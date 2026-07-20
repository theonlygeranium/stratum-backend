#!/usr/bin/env python3
"""Non-mutating STRATUM production release and governance audit."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_FRONTEND_REPO = "theonlygeranium/edstratum-v2-frontend"
DEFAULT_BACKEND_REPO = "theonlygeranium/stratum-backend"
DEFAULT_FRONTEND_URL = "https://edstratumlabs.ai"
DEFAULT_BACKEND_URL = "https://stratum-backend-production-a340.up.railway.app"
FRONTEND_CI_CONTEXT = "CI / build-and-test"
BACKEND_CI_CONTEXT = "Backend CI / pytest-and-rag"
RAILWAY_STATUS_CONTEXT = "sunny-ambition - stratum-backend"
DEFAULT_FRONTEND_FLAGS = {
    "ragEnabled": True,
    "voiceEnabled": False,
    "persistenceEnabled": False,
}
DEFAULT_FRONTEND_MAX_INTAKE_QUESTIONS = 7
DEFAULT_BACKEND_RUNTIME = {
    "graph_runtime": "langgraph",
    "session_store_backend": "postgres",
    "embedding_provider": "hash",
    "vector_store_provider": "chroma",
    "llm_provider": "writer",
}
DEFAULT_BACKEND_TTS_STATUS = "unconfigured"
DEFAULT_ACTIVATION_PROFILE = "current"
ACTIVATION_PROFILES: dict[str, dict[str, Any]] = {
    "current": {},
    "managed-rag": {
        "backend_runtime": {
            "embedding_provider": "openai",
            "vector_store_provider": "pinecone",
        },
    },
    "voice": {
        "frontend_flags": {
            "voiceEnabled": True,
        },
        "backend_tts_status": "ok",
    },
    "persistence": {
        "frontend_flags": {
            "persistenceEnabled": True,
        },
    },
    "edge-voice": {
        "frontend_flags": {
            "voiceEnabled": True,
            "persistenceEnabled": True,
        },
        "backend_tts_status": "ok",
    },
    "full-activation": {
        "frontend_flags": {
            "voiceEnabled": True,
            "persistenceEnabled": True,
        },
        "backend_runtime": {
            "embedding_provider": "openai",
            "vector_store_provider": "pinecone",
        },
        "backend_tts_status": "ok",
    },
}
FRONTEND_FLAG_ENV = {
    "ragEnabled": "STRATUM_AUDIT_EXPECT_RAG_ENABLED",
    "voiceEnabled": "STRATUM_AUDIT_EXPECT_VOICE_ENABLED",
    "persistenceEnabled": "STRATUM_AUDIT_EXPECT_PERSISTENCE_ENABLED",
}
FRONTEND_FLAG_DESTS = {
    "ragEnabled": "expected_rag_enabled",
    "voiceEnabled": "expected_voice_enabled",
    "persistenceEnabled": "expected_persistence_enabled",
}
FRONTEND_MAX_INTAKE_QUESTIONS_ENV = "STRATUM_AUDIT_EXPECT_MAX_INTAKE_QUESTIONS"
BACKEND_RUNTIME_ENV = {
    "graph_runtime": "STRATUM_AUDIT_EXPECT_GRAPH_RUNTIME",
    "session_store_backend": "STRATUM_AUDIT_EXPECT_SESSION_STORE_BACKEND",
    "embedding_provider": "STRATUM_AUDIT_EXPECT_EMBEDDING_PROVIDER",
    "vector_store_provider": "STRATUM_AUDIT_EXPECT_VECTOR_STORE_PROVIDER",
    "llm_provider": "STRATUM_AUDIT_EXPECT_LLM_PROVIDER",
}
BACKEND_TTS_STATUS_ENV = "STRATUM_AUDIT_EXPECT_TTS_STATUS"
BACKEND_RUNTIME_ALLOWED_VALUES = {
    "graph_runtime": {"langgraph", "procedural"},
    "session_store_backend": {"postgres", "memory"},
    "embedding_provider": {"hash", "openai"},
    "vector_store_provider": {"chroma", "memory", "pinecone"},
    "llm_provider": {"writer", "openai"},
}
BACKEND_TTS_STATUS_ALLOWED_VALUES = {"ok", "unconfigured"}


@dataclass
class Record:
    level: str
    name: str
    detail: str = ""


@dataclass(frozen=True)
class RuntimeExpectations:
    frontend_flags: dict[str, bool]
    frontend_max_intake_questions: int
    backend_runtime: dict[str, str]
    backend_tts_status: str


class Audit:
    def __init__(self) -> None:
        self.records: list[Record] = []

    @property
    def blockers(self) -> int:
        return sum(1 for record in self.records if record.level == "BLOCKED")

    @property
    def warnings(self) -> int:
        return sum(1 for record in self.records if record.level == "WARN")

    def ok(self, name: str, detail: str = "") -> None:
        self._record("OK", name, detail)

    def warn(self, name: str, detail: str = "") -> None:
        self._record("WARN", name, detail)

    def blocked(self, name: str, detail: str = "") -> None:
        self._record("BLOCKED", name, detail)

    def _record(self, level: str, name: str, detail: str = "") -> None:
        self.records.append(Record(level, name, detail))
        label = f"[{level}]".ljust(10)
        suffix = f": {detail}" if detail else ""
        print(f"{label} {name}{suffix}")


class GhError(RuntimeError):
    pass


def api_path(value: str) -> str:
    return value.replace("https://api.github.com/", "")


def gh_json(path: str) -> Any:
    if not shutil.which("gh"):
        raise GhError("GitHub CLI `gh` is not installed")

    result = subprocess.run(
        ["gh", "api", api_path(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "gh api failed").strip()
        raise GhError(message)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GhError(f"gh api did not return JSON: {exc}") from exc


def fetch_json(
    url: str,
    timeout: float = 15.0,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    request_headers = {
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "User-Agent": "stratum-live-release-audit",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            headers = {key.lower(): value for key, value in response.headers.items()}
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        headers = {key.lower(): value for key, value in exc.headers.items()}
        text = exc.read().decode("utf-8", errors="replace")
    body = json.loads(text)
    return status, body, headers


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError("must be a boolean: true/false, yes/no, on/off, or 1/0")


def argparse_bool(value: str) -> bool:
    try:
        return parse_bool(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_positive_int(value: str) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError("must be a positive integer") from exc
    if parsed < 1:
        raise ValueError("must be a positive integer")
    return parsed


def argparse_positive_int(value: str) -> int:
    try:
        return parse_positive_int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def validate_expected_backend_runtime(key: str, value: str) -> str:
    normalized = value.strip().lower()
    allowed = BACKEND_RUNTIME_ALLOWED_VALUES[key]
    if normalized not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"{key} must be one of: {expected}")
    return normalized


def validate_expected_tts_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in BACKEND_TTS_STATUS_ALLOWED_VALUES:
        expected = ", ".join(sorted(BACKEND_TTS_STATUS_ALLOWED_VALUES))
        raise ValueError(f"TTS status must be one of: {expected}")
    return normalized


def argparse_backend_runtime_value(key: str) -> Callable[[str], str]:
    def parse(value: str) -> str:
        try:
            return validate_expected_backend_runtime(key, value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    return parse


def argparse_tts_status(value: str) -> str:
    try:
        return validate_expected_tts_status(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def expectations_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> RuntimeExpectations:
    profile = ACTIVATION_PROFILES[args.activation_profile]

    frontend_flags = dict(DEFAULT_FRONTEND_FLAGS)
    frontend_flags.update(profile.get("frontend_flags", {}))

    frontend_max_intake_questions = int(
        profile.get("frontend_max_intake_questions", DEFAULT_FRONTEND_MAX_INTAKE_QUESTIONS)
    )

    backend_runtime = dict(DEFAULT_BACKEND_RUNTIME)
    backend_runtime.update(profile.get("backend_runtime", {}))

    backend_tts_status = str(
        profile.get("backend_tts_status", DEFAULT_BACKEND_TTS_STATUS)
    )

    for key, env_name in FRONTEND_FLAG_ENV.items():
        raw = os.getenv(env_name)
        if raw is None:
            continue
        try:
            frontend_flags[key] = parse_bool(raw)
        except ValueError as exc:
            parser.error(f"{env_name}: {exc}")

    raw_max_intake_questions = os.getenv(FRONTEND_MAX_INTAKE_QUESTIONS_ENV)
    if raw_max_intake_questions is not None:
        try:
            frontend_max_intake_questions = parse_positive_int(raw_max_intake_questions)
        except ValueError as exc:
            parser.error(f"{FRONTEND_MAX_INTAKE_QUESTIONS_ENV}: {exc}")

    for key, env_name in BACKEND_RUNTIME_ENV.items():
        raw = os.getenv(env_name)
        if raw is None:
            continue
        try:
            backend_runtime[key] = validate_expected_backend_runtime(key, raw)
        except ValueError as exc:
            parser.error(f"{env_name}: {exc}")

    raw_tts_status = os.getenv(BACKEND_TTS_STATUS_ENV)
    if raw_tts_status is not None:
        try:
            backend_tts_status = validate_expected_tts_status(raw_tts_status)
        except ValueError as exc:
            parser.error(f"{BACKEND_TTS_STATUS_ENV}: {exc}")

    for key in FRONTEND_FLAG_ENV:
        value = getattr(args, FRONTEND_FLAG_DESTS[key])
        if value is not None:
            frontend_flags[key] = value

    if args.expected_max_intake_questions is not None:
        frontend_max_intake_questions = args.expected_max_intake_questions

    for key in BACKEND_RUNTIME_ENV:
        value = getattr(args, f"expected_{key}")
        if value is not None:
            backend_runtime[key] = value

    if args.expected_tts_status is not None:
        backend_tts_status = args.expected_tts_status

    return RuntimeExpectations(
        frontend_flags=frontend_flags,
        frontend_max_intake_questions=frontend_max_intake_questions,
        backend_runtime=backend_runtime,
        backend_tts_status=backend_tts_status,
    )


def first_annotation(check_run: dict[str, Any]) -> str:
    count = check_run.get("output", {}).get("annotations_count") or 0
    annotations_url = check_run.get("output", {}).get("annotations_url")
    if not count or not annotations_url:
        return ""
    try:
        annotations = gh_json(str(annotations_url))
    except GhError as exc:
        return f"annotation lookup failed: {exc}"
    if not annotations:
        return ""
    message = annotations[0].get("message")
    return str(message or "")


def branch_required_contexts(repo: str) -> set[str]:
    status_checks = gh_json(f"repos/{repo}/branches/main/protection/required_status_checks")
    contexts = set(status_checks.get("contexts") or [])
    for check in status_checks.get("checks") or []:
        context = check.get("context")
        if context:
            contexts.add(str(context))
    return contexts


def inspect_branch(audit: Audit, repo: str, required_context: str) -> str | None:
    try:
        branch = gh_json(f"repos/{repo}/branches/main")
    except GhError as exc:
        audit.blocked(f"{repo} main branch lookup", str(exc))
        return None

    sha = branch.get("commit", {}).get("sha")
    protected = bool(branch.get("protected"))
    if not isinstance(sha, str) or len(sha) < 7:
        audit.blocked(f"{repo} main SHA", "branch response did not include a commit SHA")
        return None

    audit.ok(f"{repo} main HEAD", sha[:7])
    if not protected:
        audit.blocked(
            f"{repo} branch protection",
            f"`main` is unprotected; require `{required_context}` before release merges",
        )
        return sha

    audit.ok(f"{repo} branch protection is enabled")
    try:
        contexts = branch_required_contexts(repo)
    except GhError as exc:
        audit.blocked(f"{repo} required status checks", str(exc))
        return sha

    if required_context in contexts:
        audit.ok(f"{repo} requires status context", required_context)
    else:
        audit.blocked(
            f"{repo} required status context",
            f"missing `{required_context}`; configured contexts: {sorted(contexts) or 'none'}",
        )
    return sha


def inspect_check_run(audit: Audit, repo: str, sha: str, name: str) -> None:
    try:
        payload = gh_json(f"repos/{repo}/commits/{sha}/check-runs")
    except GhError as exc:
        audit.blocked(f"{repo} check-runs", str(exc))
        return

    runs = payload.get("check_runs") or []
    matches = [run for run in runs if run.get("name") == name]
    if not matches:
        audit.blocked(f"{repo} check `{name}`", "not found on the main commit")
        return

    run = matches[0]
    status = run.get("status")
    conclusion = run.get("conclusion")
    if status == "completed" and conclusion == "success":
        audit.ok(f"{repo} check `{name}`", "success")
        return

    detail = f"status={status} conclusion={conclusion}"
    annotation = first_annotation(run)
    if annotation:
        detail = f"{detail}; {annotation}"
    audit.blocked(f"{repo} check `{name}`", detail)


def inspect_combined_status(audit: Audit, repo: str, sha: str, context: str) -> None:
    try:
        payload = gh_json(f"repos/{repo}/commits/{sha}/status")
    except GhError as exc:
        audit.blocked(f"{repo} commit status `{context}`", str(exc))
        return

    matches = [status for status in payload.get("statuses") or [] if status.get("context") == context]
    if not matches:
        audit.blocked(f"{repo} commit status `{context}`", "not found on the main commit")
        return

    status = matches[0]
    state = status.get("state")
    description = str(status.get("description") or "")
    if state == "success":
        audit.ok(f"{repo} commit status `{context}`", description or "success")
    else:
        audit.blocked(f"{repo} commit status `{context}`", f"state={state}; {description}")


def inspect_frontend_public(
    audit: Audit,
    frontend_url: str,
    expected_sha: str | None,
    expected_backend_url: str,
    expectations: RuntimeExpectations,
) -> None:
    manifest_url = f"{frontend_url}/build-manifest.json?release-audit={int(time.time())}"
    try:
        status, manifest, headers = fetch_json(manifest_url)
    except Exception as exc:  # noqa: BLE001 - audit should report any public fetch failure.
        audit.blocked("frontend build manifest", str(exc))
        return

    if status == 200:
        audit.ok("frontend build manifest returns HTTP 200")
    else:
        audit.blocked("frontend build manifest returns HTTP 200", str(status))

    short_sha = str(manifest.get("commitShortSha") or "")
    full_sha = str(manifest.get("commitSha") or "")
    if expected_sha:
        if full_sha == expected_sha or short_sha == expected_sha[:7] or full_sha.startswith(expected_sha):
            audit.ok("frontend manifest matches GitHub main", short_sha or full_sha)
        else:
            audit.blocked(
                "frontend manifest matches GitHub main",
                f"manifest={short_sha or full_sha or 'missing'} expected={expected_sha[:7]}",
            )
    elif short_sha:
        audit.ok("frontend manifest includes commit", short_sha)
    else:
        audit.blocked("frontend manifest includes commit", "missing commitShortSha")

    cache_control = headers.get("cache-control", "")
    if "max-age=60" in cache_control:
        audit.ok("frontend manifest cache window", cache_control)
    else:
        audit.warn("frontend manifest cache window", cache_control or "missing")

    if manifest.get("backendUrl") == expected_backend_url:
        audit.ok("frontend manifest backend URL", expected_backend_url)
    else:
        audit.blocked(
            "frontend manifest backend URL",
            f"manifest={manifest.get('backendUrl')!r} expected={expected_backend_url!r}",
        )

    assets = manifest.get("assets")
    if isinstance(assets, list) and len(assets) >= 5:
        audit.ok("frontend manifest lists hashed assets", f"{len(assets)} assets")
    else:
        audit.blocked("frontend manifest lists hashed assets", "asset list missing or too short")

    try:
        config_status, config, _ = fetch_json(f"{frontend_url}/api/config")
    except Exception as exc:  # noqa: BLE001
        audit.blocked("frontend /api/config", str(exc))
        return

    if config_status == 200:
        audit.ok("frontend /api/config returns HTTP 200")
    else:
        audit.blocked("frontend /api/config returns HTTP 200", str(config_status))

    for key, expected in expectations.frontend_flags.items():
        value = config.get(key)
        if value == expected:
            audit.ok(f"frontend runtime flag {key}", str(value).lower())
        else:
            audit.blocked(f"frontend runtime flag {key}", f"got {value!r}, expected {expected!r}")

    max_intake_questions = config.get("maxIntakeQuestions")
    if max_intake_questions == expectations.frontend_max_intake_questions:
        audit.ok("frontend runtime maxIntakeQuestions", str(max_intake_questions))
    else:
        audit.blocked(
            "frontend runtime maxIntakeQuestions",
            f"got {max_intake_questions!r}, expected {expectations.frontend_max_intake_questions!r}",
        )


def inspect_backend_public(
    audit: Audit,
    backend_url: str,
    expectations: RuntimeExpectations,
) -> None:
    try:
        health_status, health, headers = fetch_json(
            f"{backend_url}/api/health",
            headers={"Origin": DEFAULT_FRONTEND_URL},
        )
    except Exception as exc:  # noqa: BLE001
        audit.blocked("backend /api/health", str(exc))
        return

    if health_status == 200:
        audit.ok("backend /api/health returns HTTP 200")
    else:
        audit.blocked("backend /api/health returns HTTP 200", str(health_status))
    if health.get("status") == "healthy" and health.get("backend_enabled") is True:
        audit.ok("backend health status", "healthy backend_enabled=true")
    else:
        audit.blocked("backend health status", json.dumps(health, sort_keys=True)[:240])
    if health.get("rag", {}).get("status") == "ok" and health.get("rag", {}).get("vectorStoreConnected") is True:
        audit.ok("backend RAG health", "ok vectorStoreConnected=true")
    else:
        audit.blocked("backend RAG health", json.dumps(health.get("rag"), sort_keys=True))
    tts_status = health.get("tts", {}).get("status")
    if tts_status == expectations.backend_tts_status:
        audit.ok("backend TTS status", str(tts_status))
    else:
        audit.blocked(
            "backend TTS status",
            f"got {tts_status!r}, expected {expectations.backend_tts_status!r}",
        )
    if headers.get("access-control-allow-origin") == DEFAULT_FRONTEND_URL:
        audit.ok("backend production CORS origin", DEFAULT_FRONTEND_URL)
    else:
        audit.blocked(
            "backend production CORS origin",
            headers.get("access-control-allow-origin") or "missing",
        )

    try:
        runtime_status, runtime, _ = fetch_json(f"{backend_url}/api/runtime")
    except Exception as exc:  # noqa: BLE001
        audit.blocked("backend /api/runtime", str(exc))
        return

    if runtime_status == 200:
        audit.ok("backend /api/runtime returns HTTP 200")
    else:
        audit.blocked("backend /api/runtime returns HTTP 200", str(runtime_status))

    for key, expected in expectations.backend_runtime.items():
        value = runtime.get(key)
        if value == expected:
            audit.ok(f"backend runtime {key}", str(value))
        else:
            audit.blocked(f"backend runtime {key}", f"got {value!r}, expected {expected!r}")

    for key in ("database_configured", "llm_configured", "notifications_configured", "required_cors_origins_present"):
        if runtime.get(key) is True:
            audit.ok(f"backend runtime {key}", "true")
        else:
            audit.blocked(f"backend runtime {key}", f"got {runtime.get(key)!r}")


def inspect_deployed_conversation_matrix(
    audit: Audit,
    backend_url: str,
    *,
    timeout: float,
    max_cases: int | None,
) -> dict[str, Any] | None:
    try:
        from scripts.eval_deployed_conversations import evaluate_deployed
    except Exception as exc:  # noqa: BLE001
        audit.blocked("deployed conversation matrix import", str(exc))
        return None

    try:
        report = evaluate_deployed(
            backend_url,
            timeout=timeout,
            max_cases=max_cases,
        )
    except Exception as exc:  # noqa: BLE001
        audit.blocked("deployed conversation matrix", f"{type(exc).__name__}: {exc}")
        return None

    metrics = report.get("metrics") or {}
    latency = metrics.get("first_token_latency_ms") or {}
    detail = (
        f"{metrics.get('scenario_count')} scenarios; "
        f"contract={metrics.get('contract_pass_rate')}; "
        f"expected={metrics.get('expected_behavior_pass_rate')}; "
        f"persona={metrics.get('persona_consistency_rate')}; "
        f"hallucination={metrics.get('no_hallucination_proxy')}; "
        f"substance={metrics.get('answer_substance_rate')}; "
        f"escalation={metrics.get('scripted_escalation_rate')}; "
        f"first_token_p95_ms={latency.get('p95')}"
    )
    if report.get("passed") is True:
        audit.ok("deployed conversation matrix", detail)
    else:
        failures = report.get("failures") or []
        failure_names = ", ".join(str(item.get("name")) for item in failures[:5])
        suffix = f"; first failures: {failure_names}" if failure_names else ""
        audit.blocked("deployed conversation matrix", f"{detail}{suffix}")
    return report


def summarize_conversation_matrix(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if report is None:
        return None
    metrics = report.get("metrics") or {}
    latency = metrics.get("first_token_latency_ms") or {}
    return {
        "passed": report.get("passed"),
        "scenarioCount": metrics.get("scenario_count"),
        "contractPassRate": metrics.get("contract_pass_rate"),
        "expectedBehaviorPassRate": metrics.get("expected_behavior_pass_rate"),
        "personaConsistencyRate": metrics.get("persona_consistency_rate"),
        "noHallucinationProxy": metrics.get("no_hallucination_proxy"),
        "answerSubstanceRate": metrics.get("answer_substance_rate"),
        "scriptedEscalationRate": metrics.get("scripted_escalation_rate"),
        "firstTokenP95Ms": latency.get("p95"),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit STRATUM public release state and GitHub governance without mutating "
            "Cloudflare, Railway, or repository settings."
        )
    )
    parser.add_argument("--frontend-repo", default=DEFAULT_FRONTEND_REPO)
    parser.add_argument("--backend-repo", default=DEFAULT_BACKEND_REPO)
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--skip-github", action="store_true", help="Only check public runtime endpoints.")
    parser.add_argument(
        "--activation-profile",
        choices=sorted(ACTIVATION_PROFILES),
        default=DEFAULT_ACTIVATION_PROFILE,
        help=(
            "Named expectation bundle for staged activation proof. "
            "`current` matches today's gated-off production runtime; "
            "`managed-rag` expects OpenAI/Pinecone; `voice` expects voice/TTS on; "
            "`persistence` expects conversation persistence on; "
            "`edge-voice` expects Cloudflare storage plus voice/persistence on while "
            "managed RAG stays on the current hash/Chroma runtime; "
            "`full-activation` combines managed RAG, voice, and persistence. "
            "Specific --expected-* flags and STRATUM_AUDIT_EXPECT_* env vars still override the profile."
        ),
    )
    parser.add_argument(
        "--include-conversation-matrix",
        action="store_true",
        help="Also run the safe deployed 50+ scenario Phase 4 conversation matrix.",
    )
    parser.add_argument(
        "--conversation-timeout",
        type=float,
        default=90.0,
        help="Per-request timeout for --include-conversation-matrix.",
    )
    parser.add_argument(
        "--conversation-max-cases",
        type=int,
        help="Debug-only cap for the conversation matrix; capped runs cannot satisfy the 50+ case SOT gate.",
    )
    expectations = parser.add_argument_group("runtime expectations")
    expectations.add_argument(
        "--expected-rag-enabled",
        dest="expected_rag_enabled",
        type=argparse_bool,
        metavar="{true,false}",
        help=f"Expected frontend /api/config ragEnabled value. Env: {FRONTEND_FLAG_ENV['ragEnabled']}.",
    )
    expectations.add_argument(
        "--expected-voice-enabled",
        dest="expected_voice_enabled",
        type=argparse_bool,
        metavar="{true,false}",
        help=f"Expected frontend /api/config voiceEnabled value. Env: {FRONTEND_FLAG_ENV['voiceEnabled']}.",
    )
    expectations.add_argument(
        "--expected-persistence-enabled",
        dest="expected_persistence_enabled",
        type=argparse_bool,
        metavar="{true,false}",
        help=(
            "Expected frontend /api/config persistenceEnabled value. "
            f"Env: {FRONTEND_FLAG_ENV['persistenceEnabled']}."
        ),
    )
    expectations.add_argument(
        "--expected-max-intake-questions",
        type=argparse_positive_int,
        metavar="N",
        help=(
            "Expected frontend /api/config maxIntakeQuestions value. "
            f"Env: {FRONTEND_MAX_INTAKE_QUESTIONS_ENV}."
        ),
    )
    expectations.add_argument(
        "--expected-graph-runtime",
        type=argparse_backend_runtime_value("graph_runtime"),
        metavar="{langgraph,procedural}",
        help=f"Expected backend /api/runtime graph_runtime. Env: {BACKEND_RUNTIME_ENV['graph_runtime']}.",
    )
    expectations.add_argument(
        "--expected-session-store-backend",
        type=argparse_backend_runtime_value("session_store_backend"),
        metavar="{memory,postgres}",
        help=(
            "Expected backend /api/runtime session_store_backend. "
            f"Env: {BACKEND_RUNTIME_ENV['session_store_backend']}."
        ),
    )
    expectations.add_argument(
        "--expected-embedding-provider",
        type=argparse_backend_runtime_value("embedding_provider"),
        metavar="{hash,openai}",
        help=(
            "Expected backend /api/runtime embedding_provider. "
            f"Env: {BACKEND_RUNTIME_ENV['embedding_provider']}."
        ),
    )
    expectations.add_argument(
        "--expected-vector-store-provider",
        type=argparse_backend_runtime_value("vector_store_provider"),
        metavar="{chroma,memory,pinecone}",
        help=(
            "Expected backend /api/runtime vector_store_provider. "
            f"Env: {BACKEND_RUNTIME_ENV['vector_store_provider']}."
        ),
    )
    expectations.add_argument(
        "--expected-llm-provider",
        type=argparse_backend_runtime_value("llm_provider"),
        metavar="{openai,writer}",
        help=f"Expected backend /api/runtime llm_provider. Env: {BACKEND_RUNTIME_ENV['llm_provider']}.",
    )
    expectations.add_argument(
        "--expected-tts-status",
        type=argparse_tts_status,
        metavar="{ok,unconfigured}",
        help=f"Expected backend /api/health tts.status. Env: {BACKEND_TTS_STATUS_ENV}.",
    )

    args = parser.parse_args(argv)
    args.expectations = expectations_from_args(args, parser)
    return args


def main() -> int:
    args = parse_args()
    audit = Audit()
    expectations: RuntimeExpectations = args.expectations

    frontend_url = args.frontend_url.rstrip("/")
    backend_url = args.backend_url.rstrip("/")

    print("STRATUM live release audit")
    print(f"Frontend: {frontend_url}")
    print(f"Backend:  {backend_url}")
    print()

    frontend_sha: str | None = None
    backend_sha: str | None = None

    if args.skip_github:
        audit.warn("GitHub governance checks skipped", "--skip-github was set")
    else:
        frontend_sha = inspect_branch(audit, args.frontend_repo, FRONTEND_CI_CONTEXT)
        if frontend_sha:
            inspect_check_run(audit, args.frontend_repo, frontend_sha, "Cloudflare Pages")
            inspect_check_run(audit, args.frontend_repo, frontend_sha, "Build, lint & test")

        backend_sha = inspect_branch(audit, args.backend_repo, BACKEND_CI_CONTEXT)
        if backend_sha:
            inspect_combined_status(audit, args.backend_repo, backend_sha, RAILWAY_STATUS_CONTEXT)
            inspect_check_run(audit, args.backend_repo, backend_sha, "Pytest & RAG eval")

    print()
    inspect_frontend_public(audit, frontend_url, frontend_sha, backend_url, expectations)
    print()
    inspect_backend_public(audit, backend_url, expectations)
    conversation_matrix: dict[str, Any] | None = None
    if args.include_conversation_matrix:
        print()
        conversation_matrix = inspect_deployed_conversation_matrix(
            audit,
            backend_url,
            timeout=args.conversation_timeout,
            max_cases=args.conversation_max_cases,
        )

    print()
    print(
        json.dumps(
            {
                "frontendUrl": frontend_url,
                "backendUrl": backend_url,
                "frontendMain": frontend_sha[:7] if frontend_sha else None,
                "backendMain": backend_sha[:7] if backend_sha else None,
                "activationProfile": args.activation_profile,
                "conversationMatrix": summarize_conversation_matrix(conversation_matrix),
                "expectations": {
                    "frontendFlags": expectations.frontend_flags,
                    "frontendMaxIntakeQuestions": expectations.frontend_max_intake_questions,
                    "backendRuntime": expectations.backend_runtime,
                    "backendTtsStatus": expectations.backend_tts_status,
                },
                "warnings": audit.warnings,
                "blockers": audit.blockers,
            },
            indent=2,
        )
    )

    if audit.blockers:
        print()
        print("Release audit blocked. Resolve the BLOCKED items before claiming full production governance.")
        return 1

    print()
    print("Release audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
