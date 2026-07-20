#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import StreamEvent


DEFAULT_BACKEND_URL = "https://stratum-backend-production-a340.up.railway.app"
DEFAULT_ORIGIN = "https://edstratumlabs.ai"
EVENT_ADAPTER = TypeAdapter(StreamEvent)


class Smoke:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, name: str, detail: str = "") -> None:
        print(f"[OK]   {name}{': ' + detail if detail else ''}")

    def fail(self, name: str, detail: str = "") -> None:
        self.failures += 1
        print(f"[FAIL] {name}{': ' + detail if detail else ''}")

    def expect(self, condition: bool, name: str, detail: str = "") -> None:
        if condition:
            self.ok(name, detail)
        else:
            self.fail(name, detail)


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/")


def json_get(client: httpx.Client, url: str, headers: dict[str, str] | None = None) -> tuple[httpx.Response, Any]:
    response = client.get(url, headers=headers)
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"parse_error": response.text[:160]}
    return response, body


def stream_chat(
    client: httpx.Client,
    backend_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    response_status: int | None = None
    content_type: str | None = None

    with client.stream(
        "POST",
        f"{backend_url}/api/chat",
        json=payload,
        headers={
            "Accept": "text/event-stream",
            "X-Stratum-Eval": "true",
        },
    ) as response:
        response_status = response.status_code
        content_type = response.headers.get("content-type")
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data:"):
                continue

            raw = line.split(":", 1)[1].strip()
            try:
                event = json.loads(raw)
                EVENT_ADAPTER.validate_python(event)
                event["_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
                events.append(event)
            except (json.JSONDecodeError, ValidationError) as exc:
                validation_errors.append(str(exc))

    event_types = [event.get("type") for event in events]
    return {
        "response_status": response_status,
        "content_type": content_type,
        "events": events,
        "event_types": event_types,
        "validation_errors": validation_errors,
        "first_token_ms": next(
            (event["_elapsed_ms"] for event in events if event.get("type") == "token"),
            None,
        ),
        "source": next((event.get("source") for event in events if event.get("type") == "source"), None),
        "citations": next((event.get("data") for event in events if event.get("type") == "citations"), []),
        "done": events[-1] if events and events[-1].get("type") == "done" else None,
    }


def base_payload(content: str, *, mode: str, session_id: str) -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": content, "timestamp": 0}],
        "mode": mode,
        "intakeIndex": None,
        "intakeAnswers": {},
        "sessionId": session_id,
    }


def check_stream_contract(smoke: Smoke, detail: dict[str, Any], name: str) -> None:
    event_types = detail["event_types"]
    smoke.expect(detail["response_status"] == 200, f"{name} returns HTTP 200", str(detail["response_status"]))
    smoke.expect(
        bool(detail["content_type"] and detail["content_type"].startswith("text/event-stream")),
        f"{name} is text/event-stream",
        str(detail["content_type"]),
    )
    smoke.expect(not detail["validation_errors"], f"{name} events validate")
    smoke.expect(bool(event_types), f"{name} emits events")
    smoke.expect(event_types[:1] == ["phase"], f"{name} first event is phase", ",".join(event_types[:3]))
    smoke.expect(event_types[-1:] == ["done"], f"{name} terminal event is done", ",".join(event_types[-3:]))
    smoke.expect(event_types.count("done") == 1, f"{name} emits one done event", str(event_types.count("done")))
    smoke.expect("error" not in event_types, f"{name} emits no error event")


def run(args: argparse.Namespace) -> int:
    smoke = Smoke()
    backend_url = normalize_url(args.url)
    run_id = uuid.uuid4().hex[:8]
    print(f"STRATUM backend live smoke: {backend_url}")

    with httpx.Client(timeout=args.timeout) as client:
        health_response, health = json_get(client, f"{backend_url}/api/health")
        smoke.expect(health_response.status_code == 200, "/api/health returns HTTP 200", str(health_response.status_code))
        smoke.expect(health.get("status") == "healthy", "/api/health reports healthy", str(health.get("status")))
        smoke.expect(health.get("backend_enabled") is True, "/api/health reports backend_enabled true")
        smoke.expect(health.get("rag", {}).get("status") == "ok", "/api/health reports RAG ok")
        smoke.expect(
            health.get("rag", {}).get("vectorStoreConnected") is True,
            "/api/health reports vector store connected",
        )
        smoke.expect(
            health.get("tts", {}).get("status") == args.expected_tts_status,
            "/api/health TTS status matches expected",
            str(health.get("tts", {}).get("status")),
        )

        cors_response, _ = json_get(
            client,
            f"{backend_url}/api/health",
            headers={"Origin": args.origin},
        )
        smoke.expect(
            cors_response.headers.get("access-control-allow-origin") == args.origin,
            "/api/health allows production CORS origin",
            cors_response.headers.get("access-control-allow-origin") or "missing",
        )

        runtime_response, runtime = json_get(client, f"{backend_url}/api/runtime")
        smoke.expect(runtime_response.status_code == 200, "/api/runtime returns HTTP 200", str(runtime_response.status_code))
        smoke.expect(runtime.get("status") == "online", "/api/runtime reports online")
        smoke.expect(runtime.get("graph_runtime") == "langgraph", "runtime graph is langgraph", str(runtime.get("graph_runtime")))
        smoke.expect(runtime.get("database_configured") is True, "runtime database is configured")
        smoke.expect(runtime.get("session_store_backend") == "postgres", "runtime session store is postgres")
        smoke.expect(
            runtime.get("session_store_database_disabled") is False,
            "runtime session store database is enabled",
        )
        smoke.expect(
            runtime.get("embedding_provider") == args.expected_embedding_provider,
            "runtime embedding provider matches expected",
            str(runtime.get("embedding_provider")),
        )
        smoke.expect(
            runtime.get("vector_store_provider") == args.expected_vector_store_provider,
            "runtime vector store provider matches expected",
            str(runtime.get("vector_store_provider")),
        )
        smoke.expect(
            runtime.get("llm_provider") == args.expected_llm_provider,
            "runtime LLM provider matches expected",
            str(runtime.get("llm_provider")),
        )
        smoke.expect(runtime.get("llm_configured") is True, "runtime LLM is configured")
        smoke.expect(runtime.get("notifications_configured") is True, "runtime notifications are configured")
        smoke.expect(
            runtime.get("required_cors_origins_present") is True,
            "runtime required CORS origins are present",
        )

        rag_payload = base_payload(
            "What does EdStratum build for RAG engineering?",
            mode="open",
            session_id=f"live-smoke-rag-{run_id}",
        )
        rag = stream_chat(client, backend_url, rag_payload)
        check_stream_contract(smoke, rag, "/api/chat RAG stream")
        smoke.expect(rag["first_token_ms"] is not None, "/api/chat RAG stream emits token")
        smoke.expect(rag["source"] and rag["source"].get("grounded") is True, "/api/chat RAG stream is grounded")
        smoke.expect(bool(rag["citations"]), "/api/chat RAG stream emits citations", str(len(rag["citations"])))
        smoke.expect(rag["done"] and rag["done"].get("escalate") is None, "/api/chat RAG stream does not escalate")

        if not args.skip_escalation:
            escalation_payload = base_payload(
                "I want to start a project and talk to the Founding leadership team.",
                mode="escalation",
                session_id=f"live-smoke-escalation-{run_id}",
            )
            escalation = stream_chat(client, backend_url, escalation_payload)
            check_stream_contract(smoke, escalation, "/api/chat suppressed escalation stream")
            done = escalation["done"] or {}
            delivery = done.get("escalation") or {}
            smoke.expect(done.get("escalate") == "explicit", "suppressed escalation emits explicit trigger", str(done.get("escalate")))
            smoke.expect(
                delivery.get("status") == "suppressed",
                "suppressed escalation does not send notification",
                str(delivery.get("status")),
            )

    print(
        json.dumps(
            {
                "backendUrl": backend_url,
                "origin": args.origin,
                "failures": smoke.failures,
                "expected": {
                    "ttsStatus": args.expected_tts_status,
                    "embeddingProvider": args.expected_embedding_provider,
                    "vectorStoreProvider": args.expected_vector_store_provider,
                    "llmProvider": args.expected_llm_provider,
                },
            },
            indent=2,
        )
    )
    return 1 if smoke.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a safe live smoke against the deployed STRATUM backend."
    )
    parser.add_argument("--url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--expected-tts-status", default="unconfigured")
    parser.add_argument("--expected-embedding-provider", default="hash")
    parser.add_argument("--expected-vector-store-provider", default="chroma")
    parser.add_argument("--expected-llm-provider", default="writer")
    parser.add_argument(
        "--skip-escalation",
        action="store_true",
        help="Skip the X-Stratum-Eval suppressed escalation contract check.",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
