from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.graph import initial_state_from_request, route_key
from app.models import ChatRequest
from app.sse import sse_event
import app.main as main_module


@pytest.fixture(autouse=True)
def _isolate_agent_state(tmp_path):
    main_module.agent.low_confidence_counts.clear()
    main_module.agent.session_store.database_url = None
    main_module.agent.session_store._db_disabled = True
    object.__setattr__(main_module.agent.settings, "escalation_log_dir", tmp_path)
    object.__setattr__(main_module.agent.settings, "resend_api_key", None)
    object.__setattr__(main_module.agent.settings, "jeffrey_email", None)


client = TestClient(main_module.app)
REQUIRED_ORIGINS = [
    "https://edstratumlabs.ai",
    "https://www.edstratumlabs.ai",
    "https://edstratumlabs.pages.dev",
    "http://localhost:5173",
]


def _events(response_text: str) -> list[dict]:
    events = []
    for block in response_text.strip().split("\n\n"):
        assert block.startswith("data: ")
        events.append(json.loads(block.removeprefix("data: ")))
    return events


def _post(payload: dict) -> list[dict]:
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    return _events(response.text)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "stratum": "online",
        "backend_enabled": True,
    }


@pytest.mark.parametrize("origin", REQUIRED_ORIGINS)
def test_required_cors_origins(origin: str) -> None:
    preflight = client.options(
        "/api/chat",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "POST" in preflight.headers["access-control-allow-methods"]

    health = client.get("/api/health", headers={"Origin": origin})
    assert health.status_code == 200
    assert health.headers["access-control-allow-origin"] == origin


def test_sse_event_rejects_invalid_contract_payload() -> None:
    with pytest.raises(ValidationError):
        sse_event({"type": "phase", "phase": "thinking"})


def test_open_mode_emits_required_sse_order() -> None:
    events = _post(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Does AI make sense for my Canvas environment?",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-open",
        }
    )
    assert [event["type"] for event in events[:4]] == [
        "phase",
        "phase",
        "phase",
        "source",
    ]
    assert events[0]["phase"] == "searching"
    assert events[1]["phase"] == "retrieving"
    assert events[2]["phase"] == "composing"
    assert set(events[3]["source"]) == {"label", "score", "grounded"}
    assert isinstance(events[3]["source"]["score"], float | int)
    assert 0 <= events[3]["source"]["score"] <= 1
    first_token_index = next(
        index for index, event in enumerate(events) if event["type"] == "token"
    )
    assert all(event["type"] == "phase" for event in events[:3])
    assert events[3]["type"] == "source"
    assert first_token_index > 3
    assert events[-1]["type"] == "done"
    assert [event["type"] for event in events].count("done") == 1
    assert events[-1] == {"type": "done", "snapshot": None, "escalate": None}
    assert any(event.get("type") == "token" for event in events)


def test_chat_stream_uses_sse_headers() -> None:
    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Does AI make sense for my Canvas environment?",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-headers",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_explicit_escalation() -> None:
    events = _post(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "I want to start a project and talk to Jeffrey.",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-explicit",
        }
    )
    assert events[0] == {"type": "phase", "phase": "escalating"}
    assert events[-1]["type"] == "done"
    assert events[-1]["escalate"] == "explicit"


def test_frontend_mock_explicit_human_trigger() -> None:
    events = _post(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Can I talk to a real person?",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-human",
        }
    )
    assert events[0] == {"type": "phase", "phase": "escalating"}
    assert events[-1]["escalate"] == "explicit"


def test_about_mode_matches_frontend_phase_shape() -> None:
    events = _post(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "What does an EdStratum engagement look like?",
                    "timestamp": 0,
                }
            ],
            "mode": "about",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-about",
        }
    )
    assert [event["type"] for event in events[:2]] == ["phase", "phase"]
    assert events[0]["phase"] == "searching"
    assert events[1]["phase"] == "composing"
    assert all(event["type"] != "source" for event in events)
    assert events[-1] == {"type": "done", "snapshot": None, "escalate": None}


def test_intake_snapshot_and_high_intent() -> None:
    events = _post(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Success is a production pilot in one department.",
                    "timestamp": 0,
                }
            ],
            "mode": "intake",
            "intakeIndex": 7,
            "intakeAnswers": {
                "org-type": "Higher Ed institution",
                "canvas-usage": "Canvas is our core LMS",
                "problem": "We want to automate advising triage",
                "data-infra": "Developing",
                "engineering": "Hybrid",
                "timeline": "30–60 days",
                "success": "A measurable pilot",
            },
            "sessionId": "contract-intake",
        }
    )
    assert events[0]["phase"] == "assessing"
    assert events[-1]["type"] == "done"
    assert events[-1]["snapshot"]["situation"]
    assert "firstStep" in events[-1]["snapshot"]
    assert "first_step" not in events[-1]["snapshot"]
    assert events[-1]["escalate"] == "high_intent"


def test_frontend_mock_three_to_six_months_high_intent() -> None:
    events = _post(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Success is a deployable pilot.",
                    "timestamp": 0,
                }
            ],
            "mode": "intake",
            "intakeIndex": 7,
            "intakeAnswers": {
                "org-type": "EdTech platform",
                "canvas-usage": "We integrate with Canvas",
                "problem": "Course content assistant",
                "data-infra": "Mature / clean",
                "engineering": "Internal team",
                "timeline": "3–6 months",
                "success": "A usable pilot",
            },
            "sessionId": "contract-intake-3-6",
        }
    )
    assert events[-1]["escalate"] == "high_intent"


def test_initial_graph_state_uses_api_contract_names() -> None:
    request = ChatRequest.model_validate(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Start the intake.",
                    "timestamp": 0,
                }
            ],
            "mode": "intake",
            "intakeIndex": 2,
            "intakeAnswers": {"org-type": "Higher Ed"},
            "sessionId": "contract-graph",
        }
    )

    state = initial_state_from_request(request)

    assert state["messages"] == request.messages
    assert state["mode"] == "intake"
    assert state["intake_index"] == 2
    assert state["intake_answers"] == {"org-type": "Higher Ed"}
    assert state["source_confidence"] is None
    assert state["escalation_trigger"] is None
    assert state["snapshot"] is None
    assert state["session_id"] == "contract-graph"
    assert route_key(state) == "intake"

    state["mode"] = "unknown"  # type: ignore[typeddict-item]
    assert route_key(state) == "open"
