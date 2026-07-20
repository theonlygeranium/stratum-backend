from __future__ import annotations

import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.escalation import build_payload, detect_direct_trigger
from app.graph import (
    build_stratum_graph,
    initial_state_from_request,
    request_from_state,
    route_key,
    route_node,
)
from app.models import (
    ChatRequest,
    EscalationDelivery,
    PhaseEvent,
    ReadinessSnapshot,
    SourceConfidence,
    StratumResult,
)
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
    object.__setattr__(main_module.agent.settings, "elevenlabs_api_key", None)


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
        "rag": {"status": "ok", "vectorStoreConnected": True},
        "tts": {"status": "unconfigured", "provider": "elevenlabs"},
    }


def test_runtime_reports_non_secret_operational_status() -> None:
    response = client.get("/api/runtime")
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "online"
    assert data["graph_runtime"] in {"langgraph", "procedural"}
    assert data["checkpointer"] in {"uninitialized", "memory", "postgres", "none"}
    assert data["session_store_backend"] in {"postgres", "memory"}
    assert data["embedding_provider"] in {"hash", "openai"}
    assert data["vector_store_provider"] in {"chroma", "memory", "pinecone"}
    assert data["reranker_provider"] in {"heuristic", "cohere"}
    assert data["required_cors_origins_present"] is True
    for key in [
        "database_configured",
        "session_store_database_disabled",
        "llm_configured",
        "openai_api_key_configured",
        "resend_configured",
        "escalation_email_configured",
        "notifications_configured",
        "allowed_origins_env_configured",
    ]:
        assert isinstance(data[key], bool)


def test_chat_request_accepts_sentiment_escalation_metadata() -> None:
    request = ChatRequest.model_validate(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "This is urgent and needs attention today.",
                    "timestamp": 0,
                }
            ],
            "mode": "escalation",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "sentiment-contract",
            "escalationTrigger": "sentiment",
            "sentimentSignal": "urgency",
        }
    )

    assert request.escalation_trigger == "sentiment"
    assert request.sentiment_signal == "urgency"
    assert request.model_dump(mode="json", by_alias=True)["sentimentSignal"] == "urgency"


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
    citations_index = next(
        index for index, event in enumerate(events) if event["type"] == "citations"
    )
    assert all(event["type"] == "phase" for event in events[:3])
    assert events[3]["type"] == "source"
    assert first_token_index > 3
    assert first_token_index < citations_index < len(events) - 1
    assert events[citations_index]["data"]
    assert set(events[citations_index]["data"][0]) == {"source", "excerpt"}
    assert events[-1]["type"] == "done"
    assert [event["type"] for event in events].count("done") == 1
    assert events[-1] == {
        "type": "done",
        "snapshot": None,
        "escalate": None,
    }
    assert any(event.get("type") == "token" for event in events)


def test_agent_stream_reaches_source_before_llm_tokens(monkeypatch) -> None:
    async def slow_llm_stream(*args, **kwargs):
        await asyncio.sleep(0)
        yield "streamed token"

    monkeypatch.setattr(
        main_module.agent,
        "_stream_grounded_response",
        slow_llm_stream,
    )
    request = ChatRequest.model_validate(
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
            "sessionId": "contract-progressive-stream",
        }
    )

    async def collect_prefix() -> list[dict]:
        events = []
        async for event in main_module.agent.stream(request):
            events.append(event.model_dump(mode="json"))
            if len(events) == 4:
                break
        return events

    events = asyncio.run(collect_prefix())

    assert [event["type"] for event in events] == [
        "phase",
        "phase",
        "phase",
        "source",
    ]
    assert [event.get("phase") for event in events[:3]] == [
        "searching",
        "retrieving",
        "composing",
    ]


def test_agent_stream_uses_graph_runtime_for_state_machine_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert main_module.agent.graph_runtime is not None
    calls = []

    async def fake_graph_respond(request: ChatRequest) -> StratumResult:
        calls.append(request.session_id)
        return StratumResult(phases=["composing"], response_text="graph-backed")

    monkeypatch.setattr(
        main_module.agent.graph_runtime,
        "respond",
        fake_graph_respond,
    )
    request = ChatRequest.model_validate(
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
            "sessionId": "contract-stream-graph-about",
        }
    )

    async def collect() -> list[dict]:
        return [
            event.model_dump(mode="json")
            async for event in main_module.agent.stream(request)
        ]

    events = asyncio.run(collect())

    assert calls == ["contract-stream-graph-about"]
    assert events[0] == {"type": "phase", "phase": "composing"}
    assert events[-1] == {
        "type": "done",
        "snapshot": None,
        "escalate": None,
        "escalation": None,
    }
    assert "graph-backed" == "".join(
        event["token"] for event in events if event["type"] == "token"
    )


def test_agent_open_stream_uses_graph_updates_and_checkpoints_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert main_module.agent.graph_runtime is not None
    calls = {"stream": [], "checkpoint": []}

    async def fake_stream_updates(request: ChatRequest, *, interrupt_after=None):
        calls["stream"].append((request.session_id, interrupt_after))
        yield "route", {"mode": "open"}
        yield "open", {
            "retrieved_context": ["Graph-prepared Canvas context."],
            "source_confidence": {
                "label": "Graph Prepared Source",
                "score": 0.97,
                "grounded": True,
            },
            "response_text": "",
            "result": None,
        }

    async def fake_checkpoint_result(
        request: ChatRequest,
        result: StratumResult,
        *,
        as_node: str = "generate",
    ) -> None:
        calls["checkpoint"].append((request.session_id, result.response_text, as_node))

    async def fake_stream_grounded_response(*args, **kwargs):
        yield "graph token"

    monkeypatch.setattr(
        main_module.agent.graph_runtime,
        "stream_updates",
        fake_stream_updates,
    )
    monkeypatch.setattr(
        main_module.agent.graph_runtime,
        "checkpoint_result",
        fake_checkpoint_result,
    )
    monkeypatch.setattr(
        main_module.agent,
        "_stream_grounded_response",
        fake_stream_grounded_response,
    )
    request = ChatRequest.model_validate(
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
            "sessionId": "contract-open-graph-stream",
        }
    )

    async def collect() -> list[dict]:
        return [
            event.model_dump(mode="json")
            async for event in main_module.agent.stream(request)
        ]

    events = asyncio.run(collect())

    assert calls["stream"] == [("contract-open-graph-stream", ["open"])]
    assert calls["checkpoint"] == [
        ("contract-open-graph-stream", "Here is the grounded read: graph token", "generate")
    ]
    assert [event["type"] for event in events[:4]] == [
        "phase",
        "phase",
        "phase",
        "source",
    ]
    assert events[3]["source"]["label"] == "Graph Prepared Source"
    assert "".join(event["token"] for event in events if event["type"] == "token") == (
        "Here is the grounded read: graph token"
    )
    assert events[-1] == {
        "type": "done",
        "snapshot": None,
        "escalate": None,
        "escalation": None,
    }


def test_agent_open_graph_stream_falls_back_when_llm_stream_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert main_module.agent.graph_runtime is not None
    calls = {"checkpoint": []}

    async def fake_stream_updates(request: ChatRequest, *, interrupt_after=None):
        yield "open", {
            "retrieved_context": ["Graph-prepared Canvas context with implementation detail."],
            "source_confidence": {
                "label": "Graph Prepared Source",
                "score": 0.97,
                "grounded": True,
            },
            "result": None,
        }

    async def fake_checkpoint_result(
        request: ChatRequest,
        result: StratumResult,
        *,
        as_node: str = "generate",
    ) -> None:
        calls["checkpoint"].append(result.response_text)

    async def fake_stream_grounded_response(*args, **kwargs):
        if False:
            yield ""

    monkeypatch.setattr(
        main_module.agent.graph_runtime,
        "stream_updates",
        fake_stream_updates,
    )
    monkeypatch.setattr(
        main_module.agent.graph_runtime,
        "checkpoint_result",
        fake_checkpoint_result,
    )
    monkeypatch.setattr(
        main_module.agent,
        "_stream_grounded_response",
        fake_stream_grounded_response,
    )
    request = ChatRequest.model_validate(
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
            "sessionId": "contract-open-graph-empty-stream",
        }
    )

    async def collect() -> list[dict]:
        return [
            event.model_dump(mode="json")
            async for event in main_module.agent.stream(request)
        ]

    events = asyncio.run(collect())
    text = "".join(event["token"] for event in events if event["type"] == "token")

    assert text.startswith("Here is the grounded read: ")
    assert "Based on Graph Prepared Source" in text
    assert "Graph-prepared Canvas context with implementation detail." in text
    assert calls["checkpoint"] == [text]


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


def test_chat_stream_error_path_still_emits_terminal_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_stream(
        request: ChatRequest,
        *,
        suppress_notifications: bool = False,
    ):
        assert request.session_id == "contract-error-terminal-done"
        assert suppress_notifications is True
        yield PhaseEvent(type="phase", phase="searching")
        raise RuntimeError("forced stream failure")

    monkeypatch.setattr(main_module.agent, "stream", failing_stream)

    response = client.post(
        "/api/chat",
        headers={"X-Stratum-Eval": "true"},
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Trigger a forced stream failure.",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-error-terminal-done",
        },
    )

    events = _events(response.text)
    assert response.status_code == 200
    assert [event["type"] for event in events] == ["phase", "error", "done"]
    assert events[1]["message"].startswith("STRATUM hit an internal error")
    assert events[-1] == {"type": "done", "snapshot": None, "escalate": None}


def test_explicit_escalation() -> None:
    events = _post(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "I want to start a project and talk to the Founding leadership team.",
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
    assert events[-1]["escalation"]["status"] == "prepared"
    text = "".join(event["token"] for event in events if event["type"] == "token")
    assert "I've prepared a summary for the Founding leadership team" in text
    assert "James from the Founding leadership team" not in text
    assert "Jeffrey" not in text
    assert "Calendly" not in text
    assert "calendar" not in text.lower()


def test_confirmed_escalation_notification_copy_says_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def successful_notify(*args, **kwargs) -> EscalationDelivery:
        return EscalationDelivery(
            success=True,
            status="sent",
            messageId="test-message",
        )

    monkeypatch.setattr(main_module.agent, "_notify_only", successful_notify)
    request = ChatRequest.model_validate(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "I want to start a project and talk to the Founding leadership team.",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-confirmed-notify-copy",
        }
    )

    result = asyncio.run(main_module.agent.respond(request))

    assert "I've sent the Founding leadership team a summary" in result.response_text
    assert result.escalation is not None
    assert result.escalation.status == "sent"
    assert "They typically respond within one business day." in result.response_text
    assert "James from the Founding leadership team" not in result.response_text
    assert "I've prepared a summary" not in result.response_text
    assert "Jeffrey" not in result.response_text
    assert "Calendly" not in result.response_text


def test_eval_header_suppresses_escalation_notification(monkeypatch) -> None:
    async def qa_notify(*args, **kwargs) -> EscalationDelivery:
        assert kwargs["suppress_notifications"] is True
        return EscalationDelivery(success=True, status="suppressed")

    monkeypatch.setattr(main_module.agent, "_notify_only", qa_notify)
    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "I want to start a project and talk to the Founding leadership team.",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-eval-suppression",
        },
        headers={"X-Stratum-Eval": "true"},
    )

    events = _events(response.text)

    assert response.status_code == 200
    assert events[0] == {"type": "phase", "phase": "escalating"}
    assert events[-1]["escalate"] == "explicit"
    assert events[-1]["escalation"]["status"] == "suppressed"


def test_eval_header_suppresses_high_intent_intake_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def qa_notify(*args, **kwargs) -> EscalationDelivery:
        assert kwargs["suppress_notifications"] is True
        return EscalationDelivery(success=True, status="suppressed")

    monkeypatch.setattr(main_module.agent, "_notify_only", qa_notify)
    response = client.post(
        "/api/chat",
        json={
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
                "timeline": "30-60 days",
                "success": "A measurable pilot",
            },
            "sessionId": "contract-eval-high-intent-suppression",
        },
        headers={"X-Stratum-Eval": "true"},
    )

    events = _events(response.text)

    assert response.status_code == 200
    assert events[-1]["snapshot"]["situation"]
    assert events[-1]["escalate"] == "high_intent"
    assert events[-1]["escalation"]["status"] == "suppressed"


def test_eval_header_suppresses_confidence_escalation_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def qa_notify(*args, **kwargs) -> EscalationDelivery:
        assert kwargs["suppress_notifications"] is True
        return EscalationDelivery(success=True, status="suppressed")

    retrieval = type(
        "Retrieval",
        (),
        {
            "docs": [],
            "source": SourceConfidence(label="", score=0.0, grounded=False),
        },
    )()
    monkeypatch.setattr(main_module.agent, "_notify_only", qa_notify)
    monkeypatch.setattr(main_module.agent.retriever, "retrieve", lambda _: retrieval)
    main_module.agent.low_confidence_counts["contract-eval-confidence"] = 1

    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "How does Canvas support orbital grade sync?",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-eval-confidence",
        },
        headers={"X-Stratum-Eval": "true"},
    )

    events = _events(response.text)

    assert response.status_code == 200
    assert events[-1]["escalate"] == "confidence"
    assert events[-1]["escalation"]["status"] == "suppressed"
    assert "I've prepared a summary" in "".join(
        event["token"] for event in events if event["type"] == "token"
    )


def test_escalate_route_qa_header_returns_mock_success() -> None:
    response = client.post(
        "/api/escalate",
        json={
            "leadName": "Test Visitor",
            "leadEmail": "visitor@example.com",
            "intakeSummary": {"situation": "Testing handoff suppression"},
            "escalationReason": "explicit",
            "sessionId": "contract-route-qa",
            "timestamp": "2026-07-20T00:00:00+00:00",
        },
        headers={"X-Stratum-QA": "true"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "suppressed",
        "messageId": "qa-suppressed",
        "error": None,
    }


def test_escalate_route_returns_safe_failure_without_config() -> None:
    response = client.post(
        "/api/escalate",
        json={
            "intakeSummary": {},
            "escalationReason": "explicit",
            "sessionId": "contract-route-unconfigured",
        },
    )

    assert response.status_code == 500
    assert response.json()["success"] is False
    assert response.json()["status"] == "prepared"


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

    assert state["messages"] == [
        message.model_dump(mode="json", by_alias=True) for message in request.messages
    ]
    assert state["mode"] == "intake"
    assert state["request_mode"] == "intake"
    assert state["intake_index"] == 2
    assert state["intake_answers"] == {"org-type": "Higher Ed"}
    assert state["source_confidence"] is None
    assert state["citations"] == []
    assert state["escalation_trigger"] is None
    assert state["sentiment_signal"] is None
    assert state["escalation"] is None
    assert state["snapshot"] is None
    assert state["session_id"] == "contract-graph"
    assert route_key(state) == "intake"

    state["mode"] = "unknown"  # type: ignore[typeddict-item]
    assert route_key(state) == "open"


def test_direct_trigger_routes_without_losing_request_mode() -> None:
    request = ChatRequest.model_validate(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "I want to start a project and talk to the Founding leadership team.",
                    "timestamp": 0,
                }
            ],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-graph-route",
        }
    )
    state = initial_state_from_request(request)
    state.update(route_node(state))

    assert route_key(state) == "escalation"
    assert state["escalation_trigger"] == "explicit"
    assert request_from_state(state).mode == "open"


def test_sentiment_trigger_routes_from_request_metadata() -> None:
    request = ChatRequest.model_validate(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "I need this now.",
                    "timestamp": 0,
                }
            ],
            "mode": "escalation",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "contract-sentiment-route",
            "escalationTrigger": "sentiment",
            "sentimentSignal": "urgency",
        }
    )
    state = initial_state_from_request(request)
    state.update(route_node(state))
    routed_request = request_from_state(state)

    assert route_key(state) == "escalation"
    assert state["escalation_trigger"] == "sentiment"
    assert state["sentiment_signal"] == "urgency"
    assert routed_request.mode == "escalation"
    assert routed_request.escalation_trigger == "sentiment"
    assert routed_request.sentiment_signal == "urgency"


def test_escalation_payload_includes_sentiment_signal() -> None:
    request = ChatRequest.model_validate(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "This is urgent and I need this now.",
                    "timestamp": 0,
                }
            ],
            "mode": "escalation",
            "intakeIndex": None,
            "intakeAnswers": {"timeline": "today"},
            "sessionId": "contract-sentiment-payload",
            "escalationTrigger": "sentiment",
            "sentimentSignal": "urgency",
        }
    )

    payload = build_payload(request, "sentiment", None)

    assert payload["escalation_trigger"] == "sentiment"
    assert payload["key_signals"]["timeline"] == "today"
    assert payload["key_signals"]["sentiment_signal"] == "urgency"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I want to start a project and talk to the Founding leadership team.", "explicit"),
        ("Please connect me with the Founding leadership team.", "explicit"),
        ("How much does this cost?", "explicit"),
        ("Can I talk to a real person?", "explicit"),
        ("Can I talk to a human?", "sentiment"),
        ("This is useless.", "sentiment"),
        ("Is EdStratum founder-led?", None),
        ("Who is the Founding leadership team and what is the methodology?", None),
        ("What is the cost model for RAG evaluation?", None),
        ("How should pricing data feed an ROI model?", None),
    ],
)
def test_direct_trigger_uses_phrase_level_escalation(
    text: str,
    expected: str | None,
) -> None:
    assert detect_direct_trigger(text) == expected


def test_agent_uses_compiled_langgraph_runtime() -> None:
    assert main_module.agent.graph_runtime is not None
    compiled = main_module.agent.graph_runtime.compiled or asyncio.run(
        main_module.agent.graph_runtime._compiled_graph()
    )
    assert main_module.agent.graph_runtime.checkpointer_name in {"memory", "postgres"}
    assert {
        "route",
        "open",
        "intake",
        "assess",
        "about",
        "escalation",
        "notify",
        "generate",
    } <= set(compiled.nodes)


def test_langgraph_topology_matches_executable_spec() -> None:
    assert main_module.agent.graph_runtime is not None
    compiled = main_module.agent.graph_runtime.compiled or asyncio.run(
        main_module.agent.graph_runtime._compiled_graph()
    )
    edges = {
        (edge.source, edge.target, edge.data, edge.conditional)
        for edge in compiled.get_graph().edges
    }

    assert {
        ("__start__", "route", None, False),
        ("route", "open", None, True),
        ("route", "intake", None, True),
        ("route", "about", None, True),
        ("route", "escalation", None, True),
        ("open", "generate", None, False),
        ("about", "generate", None, False),
        ("intake", "assess", "complete", True),
        ("intake", "generate", "incomplete", True),
        ("assess", "generate", None, False),
        ("escalation", "notify", None, False),
        ("notify", "generate", None, False),
        ("generate", "__end__", None, False),
    } <= edges
    assert {
        edge.source for edge in compiled.get_graph().edges if edge.target == "__end__"
    } == {"generate"}


def test_graph_runtime_lazily_compiles_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    from langgraph.checkpoint.memory import MemorySaver

    async def fake_make_checkpointer(database_url: str | None):
        assert database_url == "postgresql://example/stratum"
        return MemorySaver(), "postgres", None

    async def open_handler(_: ChatRequest) -> StratumResult:
        return StratumResult(
            phases=["composing"],
            source=SourceConfidence(label="Test", score=1.0, grounded=True),
            response_text="ok",
        )

    monkeypatch.setattr("app.graph._make_checkpointer", fake_make_checkpointer)
    runtime = build_stratum_graph(
        database_url="postgresql://example/stratum",
        open_handler=open_handler,
        intake_handler=open_handler,
        about_handler=lambda: StratumResult(phases=["composing"], response_text="ok"),
        escalation_handler=lambda request, trigger: open_handler(request),
    )
    assert runtime is not None
    assert runtime.compiled is None
    assert runtime.checkpointer_name == "uninitialized"

    request = ChatRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "Hello", "timestamp": 0}],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "lazy-graph",
        }
    )
    result = asyncio.run(runtime.respond(request))

    assert result.response_text == "ok"
    assert runtime.compiled is not None
    assert runtime.checkpointer_name == "postgres"


def test_graph_runtime_generates_open_result_after_prepared_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langgraph.checkpoint.memory import MemorySaver

    async def fake_make_checkpointer(database_url: str | None):
        assert database_url is None
        return MemorySaver(), "memory", None

    calls = {"open": 0, "generate": 0}

    async def open_handler(_: ChatRequest) -> dict:
        calls["open"] += 1
        return {
            "retrieved_context": ["prepared context"],
            "source_confidence": {
                "label": "Prepared Source",
                "score": 0.91,
                "grounded": True,
            },
            "response_text": "",
            "result": None,
        }

    async def generate_handler(state: dict) -> StratumResult:
        calls["generate"] += 1
        assert state["retrieved_context"] == ["prepared context"]
        assert state["source_confidence"]["label"] == "Prepared Source"
        return StratumResult(
            phases=["searching", "retrieving", "composing"],
            source=SourceConfidence.model_validate(state["source_confidence"]),
            response_text="generated from prepared context",
        )

    monkeypatch.setattr("app.graph._make_checkpointer", fake_make_checkpointer)
    runtime = build_stratum_graph(
        database_url=None,
        open_handler=open_handler,
        intake_handler=lambda request: generate_handler({}),
        about_handler=lambda: StratumResult(phases=["composing"], response_text="ok"),
        escalation_handler=lambda request, trigger: generate_handler({}),
        generate_handler=generate_handler,
    )
    assert runtime is not None

    request = ChatRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "Hello", "timestamp": 0}],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "graph-generate-after-open",
        }
    )
    result = asyncio.run(runtime.respond(request))

    assert result.response_text == "generated from prepared context"
    assert result.source is not None
    assert result.source.label == "Prepared Source"
    assert calls == {"open": 1, "generate": 1}


def test_graph_adapter_nodes_preserve_single_handler_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langgraph.checkpoint.memory import MemorySaver

    async def fake_make_checkpointer(database_url: str | None):
        assert database_url is None
        return MemorySaver(), "memory", None

    calls = {"open": 0, "intake": 0, "about": 0, "escalation": 0}

    async def open_handler(_: ChatRequest) -> StratumResult:
        calls["open"] += 1
        return StratumResult(phases=["composing"], response_text="open-ok")

    async def intake_handler(request: ChatRequest) -> StratumResult:
        calls["intake"] += 1
        if request.intake_index is not None and request.intake_index >= 7:
            return StratumResult(
                phases=["assessing", "composing"],
                response_text="snapshot-ok",
                snapshot=ReadinessSnapshot(
                    situation="situation",
                    capabilities="capabilities",
                    firstStep="first step",
                ),
                escalate="high_intent",
            )
        return StratumResult(phases=["assessing", "composing"], response_text="next-ok")

    def about_handler() -> StratumResult:
        calls["about"] += 1
        return StratumResult(phases=["composing"], response_text="about-ok")

    async def escalation_handler(
        request: ChatRequest,
        trigger: str,
    ) -> StratumResult:
        calls["escalation"] += 1
        assert trigger in {"explicit", "sentiment"}
        return StratumResult(
            phases=["escalating", "composing"],
            response_text=f"escalation-{request.mode}-{trigger}",
            escalate=trigger,
        )

    monkeypatch.setattr("app.graph._make_checkpointer", fake_make_checkpointer)
    runtime = build_stratum_graph(
        database_url=None,
        open_handler=open_handler,
        intake_handler=intake_handler,
        about_handler=about_handler,
        escalation_handler=escalation_handler,
    )
    assert runtime is not None

    def payload(
        mode: str,
        session_id: str,
        *,
        content: str = "Hello",
        intake_index: int | None = None,
    ) -> ChatRequest:
        return ChatRequest.model_validate(
            {
                "messages": [{"role": "user", "content": content, "timestamp": 0}],
                "mode": mode,
                "intakeIndex": intake_index,
                "intakeAnswers": {},
                "sessionId": session_id,
            }
        )

    open_result = asyncio.run(runtime.respond(payload("open", "graph-open")))
    about_result = asyncio.run(runtime.respond(payload("about", "graph-about")))
    incomplete_result = asyncio.run(
        runtime.respond(payload("intake", "graph-intake-incomplete", intake_index=1))
    )
    complete_result = asyncio.run(
        runtime.respond(payload("intake", "graph-intake-complete", intake_index=7))
    )
    escalation_result = asyncio.run(
        runtime.respond(
            payload(
                "open",
                "graph-escalation",
                content="This is useless.",
            )
        )
    )

    assert open_result.response_text == "open-ok"
    assert about_result.response_text == "about-ok"
    assert incomplete_result.response_text == "next-ok"
    assert complete_result.response_text == "snapshot-ok"
    assert complete_result.escalate == "high_intent"
    assert escalation_result.response_text == "escalation-open-sentiment"
    assert calls == {"open": 1, "intake": 2, "about": 1, "escalation": 1}


@pytest.mark.skipif(
    not os.getenv("STRATUM_TEST_DATABASE_URL"),
    reason="set STRATUM_TEST_DATABASE_URL to run the Postgres checkpoint smoke",
)
def test_graph_runtime_uses_async_postgres_checkpointer() -> None:
    async def open_handler(_: ChatRequest) -> StratumResult:
        return StratumResult(
            phases=["composing"],
            source=SourceConfidence(label="Test", score=1.0, grounded=True),
            response_text="ok",
        )

    runtime = build_stratum_graph(
        database_url=os.environ["STRATUM_TEST_DATABASE_URL"],
        open_handler=open_handler,
        intake_handler=open_handler,
        about_handler=lambda: StratumResult(phases=["composing"], response_text="ok"),
        escalation_handler=lambda request, trigger: open_handler(request),
    )
    assert runtime is not None
    request = ChatRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "Hello", "timestamp": 0}],
            "mode": "open",
            "intakeIndex": None,
            "intakeAnswers": {},
            "sessionId": "postgres-graph",
        }
    )

    result = asyncio.run(runtime.respond(request))

    assert result.response_text == "ok"
    assert runtime.checkpointer_name == "postgres"
