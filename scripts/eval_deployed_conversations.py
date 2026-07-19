#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import statistics
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

from app.models import StreamEvent  # noqa: E402
from scripts.conversation_scenarios import SCENARIOS  # noqa: E402


DEFAULT_BACKEND_URL = "https://stratum-backend-production-a340.up.railway.app"
FIRST_TOKEN_TARGET_MS = 1500
ESCALATION_RATE_MIN = 0.15
ESCALATION_RATE_MAX = 0.25
SNAPSHOT_DELIVERY_TARGET = 0.90
GROUNDEDNESS_TARGET = 0.85
ABANDONMENT_TARGET = 0.30

EVENT_ADAPTER = TypeAdapter(StreamEvent)
HUMAN_CLAIM_PATTERNS = [
    "i am human",
    "i'm human",
    "as a human",
    "i am a person",
    "i'm a person",
    "as a person",
]
HYPE_PATTERNS = [
    "guaranteed roi",
    "guaranteed success",
    "revolutionary",
    "game-changing",
    "magic bullet",
]
FABRICATION_PATTERNS = [
    "our standard pricing",
    "our hourly rate",
    "per month",
    "named client",
    "fortune 500 client",
]


def evaluate_deployed(
    backend_url: str,
    *,
    timeout: float,
    max_cases: int | None = None,
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:10]
    scenarios = SCENARIOS[:max_cases] if max_cases else SCENARIOS
    details: list[dict[str, Any]] = []

    with httpx.Client(timeout=timeout) as client:
        for scenario in scenarios:
            details.append(_evaluate_scenario(client, backend_url, scenario, run_id))

        if max_cases is None:
            confidence_detail = _evaluate_confidence_repeat(client, backend_url, run_id)
            details.extend(confidence_detail)

    return _summarize(details)


def _evaluate_scenario(
    client: httpx.Client,
    backend_url: str,
    scenario: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    payload = copy.deepcopy(scenario["payload"])
    payload["sessionId"] = f"{payload['sessionId']}-{run_id}"
    started = time.perf_counter()
    events: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    response_status = None
    content_type = None

    try:
        with client.stream(
            "POST",
            f"{backend_url.rstrip('/')}/api/chat",
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
                elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
                raw = line.split(":", 1)[1].strip()
                try:
                    event = json.loads(raw)
                    EVENT_ADAPTER.validate_python(event)
                    event["_elapsed_ms"] = elapsed_ms
                    events.append(event)
                except (json.JSONDecodeError, ValidationError) as exc:
                    validation_errors.append(str(exc))
    except Exception as exc:
        validation_errors.append(f"{type(exc).__name__}: {exc}")

    return _detail_from_events(
        scenario=scenario,
        events=events,
        validation_errors=validation_errors,
        response_status=response_status,
        content_type=content_type,
    )


def _evaluate_confidence_repeat(
    client: httpx.Client,
    backend_url: str,
    run_id: str,
) -> list[dict[str, Any]]:
    scenario = {
        "name": "confidence-repeat-second-turn",
        "payload": {
            "messages": [
                {
                    "role": "user",
                    "content": "Can AI recommend a backpacking route in Iceland?",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "matrix-confidence-repeat",
        },
        "mode": "escalation",
        "escalate": "confidence",
    }
    first = _evaluate_scenario(client, backend_url, scenario, f"{run_id}-confidence")
    second = _evaluate_scenario(client, backend_url, scenario, f"{run_id}-confidence")
    first["name"] = "confidence-repeat-first-turn"
    first["expected_escalate"] = None
    first["expected_check_passed"] = first["done_escalate"] is None
    return [first, second]


def _detail_from_events(
    *,
    scenario: dict[str, Any],
    events: list[dict[str, Any]],
    validation_errors: list[str],
    response_status: int | None,
    content_type: str | None,
) -> dict[str, Any]:
    event_types = [event.get("type") for event in events]
    token_text = "".join(str(event.get("token", "")) for event in events)
    first_event_ms = events[0]["_elapsed_ms"] if events else None
    first_token_ms = next(
        (event["_elapsed_ms"] for event in events if event.get("type") == "token"),
        None,
    )
    source = next(
        (event.get("source") for event in events if event.get("type") == "source"),
        None,
    )
    done_event = events[-1] if events and events[-1].get("type") == "done" else {}
    sequence_errors = _sequence_errors(event_types, scenario)
    expected_check_passed = _expected_check(scenario, done_event, event_types)
    persona_passed = _persona_check(token_text)
    hallucination_passed = _hallucination_check(scenario, token_text, source)

    return {
        "name": scenario["name"],
        "mode": scenario.get("mode"),
        "response_status": response_status,
        "content_type": content_type,
        "event_counts": {
            event_type: event_types.count(event_type)
            for event_type in sorted(set(event_types))
        },
        "first_event_ms": first_event_ms,
        "first_token_ms": first_token_ms,
        "source": source,
        "done": bool(done_event),
        "done_escalate": done_event.get("escalate"),
        "done_snapshot": bool(done_event.get("snapshot")),
        "expected_escalate": scenario.get("escalate"),
        "expected_snapshot": scenario.get("snapshot"),
        "validation_errors": validation_errors,
        "sequence_errors": sequence_errors,
        "contract_passed": (
            not validation_errors
            and not sequence_errors
            and response_status == 200
            and bool(content_type and content_type.startswith("text/event-stream"))
        ),
        "expected_check_passed": expected_check_passed,
        "persona_passed": persona_passed,
        "hallucination_passed": hallucination_passed,
    }


def _sequence_errors(event_types: list[str], scenario: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not event_types:
        return ["no_events"]
    if event_types[0] != "phase":
        errors.append("first_event_not_phase")
    if event_types[-1] != "done":
        errors.append("last_event_not_done")
    if event_types.count("done") != 1:
        errors.append("done_count_not_one")
    if "error" in event_types:
        errors.append("error_event")

    first_token = _first_index(event_types, "token")
    first_source = _first_index(event_types, "source")
    first_non_phase = next(
        (index for index, event_type in enumerate(event_types) if event_type != "phase"),
        None,
    )
    if first_token is not None and any(
        event_type == "phase" for event_type in event_types[first_token + 1 :]
    ):
        errors.append("phase_after_token")
    if first_source is not None:
        if first_token is not None and first_source > first_token:
            errors.append("source_after_token")
        if first_non_phase != first_source:
            errors.append("source_not_after_phases")
    if scenario.get("mode") == "about" and first_source is not None:
        errors.append("about_mode_emitted_source")
    if scenario.get("mode") == "intake" and "escalate" not in scenario:
        first_phase = event_types[0] if event_types else None
        if first_phase != "phase":
            errors.append("intake_first_event_not_phase")
    return errors


def _expected_check(
    scenario: dict[str, Any],
    done_event: dict[str, Any],
    event_types: list[str],
) -> bool:
    if "escalate" in scenario and done_event.get("escalate") != scenario["escalate"]:
        return False
    if "snapshot" in scenario and bool(done_event.get("snapshot")) is not scenario["snapshot"]:
        return False
    if scenario.get("mode") == "open" and "escalate" not in scenario:
        return "token" in event_types
    return True


def _persona_check(text: str) -> bool:
    lowered = text.lower()
    return not any(pattern in lowered for pattern in HUMAN_CLAIM_PATTERNS + HYPE_PATTERNS)


def _hallucination_check(
    scenario: dict[str, Any],
    text: str,
    source: dict[str, Any] | None,
) -> bool:
    lowered = text.lower()
    if any(pattern in lowered for pattern in FABRICATION_PATTERNS):
        return False
    if scenario["name"] == "out-of-scope":
        return (
            "jeffrey" in lowered
            or "scoped specifically" in lowered
            or "do not have" in lowered
            or "don't have" in lowered
            or "not have enough" in lowered
        )
    if scenario.get("mode") == "open" and "escalate" not in scenario:
        return bool(source and source.get("grounded") is True)
    return True


def _summarize(details: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(details)
    first_token_values = [
        detail["first_token_ms"]
        for detail in details
        if detail["first_token_ms"] is not None
    ]
    expected_snapshots = [detail for detail in details if detail["expected_snapshot"]]
    expected_snapshot_count = len(expected_snapshots)
    delivered_snapshots = sum(1 for detail in expected_snapshots if detail["done_snapshot"])
    escalations = [detail for detail in details if detail["done_escalate"]]

    contract_rate = _rate(detail["contract_passed"] for detail in details)
    expected_rate = _rate(detail["expected_check_passed"] for detail in details)
    persona_rate = _rate(detail["persona_passed"] for detail in details)
    hallucination_rate = _rate(detail["hallucination_passed"] for detail in details)
    completion_rate = _rate(detail["done"] for detail in details)
    snapshot_rate = delivered_snapshots / expected_snapshot_count if expected_snapshot_count else 1.0
    escalation_rate = len(escalations) / total if total else 0.0
    first_token_p95 = _percentile(first_token_values, 95)

    metrics = {
        "scenario_count": total,
        "contract_pass_rate": round(contract_rate, 4),
        "expected_behavior_pass_rate": round(expected_rate, 4),
        "persona_consistency_rate": round(persona_rate, 4),
        "no_hallucination_proxy": round(hallucination_rate, 4),
        "turn_completion_rate": round(completion_rate, 4),
        "abandonment_proxy": round(1.0 - completion_rate, 4),
        "snapshot_delivery_rate": round(snapshot_rate, 4),
        "scripted_escalation_rate": round(escalation_rate, 4),
        "first_token_latency_ms": {
            "p50": round(statistics.median(first_token_values), 2)
            if first_token_values
            else None,
            "p95": round(first_token_p95, 2) if first_token_values else None,
            "max": round(max(first_token_values), 2) if first_token_values else None,
        },
    }
    passed = (
        metrics["scenario_count"] >= 50
        and contract_rate == 1.0
        and expected_rate == 1.0
        and persona_rate == 1.0
        and hallucination_rate == 1.0
        and (1.0 - completion_rate) < ABANDONMENT_TARGET
        and snapshot_rate >= SNAPSHOT_DELIVERY_TARGET
        and ESCALATION_RATE_MIN <= escalation_rate <= ESCALATION_RATE_MAX
        and first_token_p95 < FIRST_TOKEN_TARGET_MS
    )
    return {
        "passed": passed,
        "thresholds": {
            "scenario_count": 50,
            "contract_pass_rate": 1.0,
            "persona_consistency_rate": 1.0,
            "no_hallucination_proxy": 1.0,
            "snapshot_delivery_rate": SNAPSHOT_DELIVERY_TARGET,
            "scripted_escalation_rate": [
                ESCALATION_RATE_MIN,
                ESCALATION_RATE_MAX,
            ],
            "first_token_p95_ms": FIRST_TOKEN_TARGET_MS,
            "abandonment_proxy": ABANDONMENT_TARGET,
        },
        "metrics": metrics,
        "failures": [
            {
                "name": detail["name"],
                "contract_passed": detail["contract_passed"],
                "expected_check_passed": detail["expected_check_passed"],
                "persona_passed": detail["persona_passed"],
                "hallucination_passed": detail["hallucination_passed"],
                "validation_errors": detail["validation_errors"],
                "sequence_errors": detail["sequence_errors"],
                "done_escalate": detail["done_escalate"],
                "expected_escalate": detail["expected_escalate"],
            }
            for detail in details
            if not (
                detail["contract_passed"]
                and detail["expected_check_passed"]
                and detail["persona_passed"]
                and detail["hallucination_passed"]
            )
        ],
        "details": details,
    }


def _first_index(values: list[str], target: str) -> int | None:
    try:
        return values.index(target)
    except ValueError:
        return None


def _rate(values) -> float:
    values = list(values)
    if not values:
        return 1.0
    return sum(1 for value in values if value) / len(values)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the STRATUM Phase 4 conversation matrix against a deployed backend."
    )
    parser.add_argument("--url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = evaluate_deployed(args.url, timeout=args.timeout, max_cases=args.max_cases)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"passed: {report['passed']}")
        for key, value in report["metrics"].items():
            print(f"{key}: {value}")
        if report["failures"]:
            print("\nfailures:")
            for failure in report["failures"]:
                print(json.dumps(failure, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
