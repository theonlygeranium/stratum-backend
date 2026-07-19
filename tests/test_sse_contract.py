from __future__ import annotations

import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.graph import (
    build_stratum_graph,
    initial_state_from_request,
    request_from_state,
    route_key,
    route_node,
)
from app.models import ChatRequest, ReadinessSnapshot, SourceConfidence, StratumResult
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


def test_eval_header_suppresses_escalation_notification(monkeypatch) -> None:
    async def fail_notify(*args, **kwargs) -> None:
        raise AssertionError("eval smoke tests must not send notifications")

    monkeypatch.setattr(main_module.agent, "_notify_only", fail_notify)
    response = client.post(
        "/api/chat",
        json={
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
            "sessionId": "contract-eval-suppression",
        },
        headers={"X-Stratum-Eval": "true"},
    )

    events = _events(response.text)

    assert response.status_code == 200
    assert events[0] == {"type": "phase", "phase": "escalating"}
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

    assert state["messages"] == [
        message.model_dump(mode="json", by_alias=True) for message in request.messages
    ]
    assert state["mode"] == "intake"
    assert state["request_mode"] == "intake"
    assert state["intake_index"] == 2
    assert state["intake_answers"] == {"org-type": "Higher Ed"}
    assert state["source_confidence"] is None
    assert state["escalation_trigger"] is None
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
                    "content": "I want to start a project and talk to Jeffrey.",
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
