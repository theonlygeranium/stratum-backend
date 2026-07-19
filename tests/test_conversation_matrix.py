from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


client = TestClient(main_module.app)


def _base_payload(
    content: str,
    *,
    mode: str = "open",
    session_id: str,
    intake_index: int | None = None,
    intake_answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": content, "timestamp": 0}],
        "mode": mode,
        "intakeIndex": intake_index,
        "intakeAnswers": intake_answers or {},
        "sessionId": session_id,
    }


def _events(response_text: str) -> list[dict[str, Any]]:
    return [
        json.loads(block.removeprefix("data: "))
        for block in response_text.strip().split("\n\n")
        if block.strip()
    ]


def _post(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    return _events(response.text)


@pytest.fixture(autouse=True)
def _isolate_agent_state(tmp_path):
    main_module.agent.low_confidence_counts.clear()
    main_module.agent.session_store.database_url = None
    main_module.agent.session_store._db_disabled = True
    object.__setattr__(main_module.agent.settings, "escalation_log_dir", tmp_path)
    object.__setattr__(main_module.agent.settings, "resend_api_key", None)
    object.__setattr__(main_module.agent.settings, "jeffrey_email", None)


OPEN_QUESTIONS = [
    "Does AI make sense for my Canvas environment?",
    "Can you help with Canvas LTI grade passback?",
    "How do Developer Keys affect a Canvas integration?",
    "When should a Canvas tool use AGS?",
    "When does Canvas Data 2 matter?",
    "How should we think about roster sync in Canvas?",
    "What does an AI roadmap include?",
    "How do we evaluate ROI for an AI pilot?",
    "How should governance fit into an AI rollout?",
    "How do we compare build versus buy for an AI feature?",
    "What makes a RAG system grounded?",
    "Why use BM25 with semantic retrieval?",
    "How does source confidence help reduce hallucination?",
    "What does semantic chunking mean here?",
    "What does EdStratum build for RAG engineering?",
    "What professional services does EdStratum offer?",
    "How does EdStratum approach learning analytics?",
    "What is a realistic first pilot for advising triage?",
    "How do you decide whether AI is the right tool?",
    "What kind of data readiness matters before an LLM project?",
    "How does EdStratum avoid hype in AI strategy?",
    "What should a maintainable AI handoff include?",
    "What is the difference between strategy and implementation?",
    "What does a discovery audit produce?",
    "Can you explain EdStratum's layered architecture?",
]

ABOUT_QUESTIONS = [
    "What does an EdStratum engagement look like?",
    "Tell me about EdStratum Labs.",
    "What kind of company is EdStratum?",
    "Is EdStratum founder-led?",
    "What is the layered architecture philosophy?",
    "What makes EdStratum different from a generic chatbot vendor?",
    "Where is EdStratum based?",
    "How does the discovery process work?",
]

ESCALATION_QUESTIONS = [
    ("I want to start a project and talk to Jeffrey.", "explicit"),
    ("Can I talk to a real person?", "explicit"),
    ("Please connect me with the founder.", "explicit"),
    ("How much does this cost?", "explicit"),
    ("This is not helpful.", "sentiment"),
    ("You do not understand what I need.", "sentiment"),
]

INTAKE_PROGRESS = [
    (0, {}, "Starting the intake"),
    (1, {"org-type": "Higher Ed institution"}, "We are higher ed."),
    (
        2,
        {"org-type": "Higher Ed institution", "canvas-usage": "Canvas is our LMS"},
        "We use Canvas.",
    ),
    (
        3,
        {
            "org-type": "Higher Ed institution",
            "canvas-usage": "Canvas is our LMS",
            "problem": "advising triage",
        },
        "We need advising triage.",
    ),
    (
        4,
        {
            "org-type": "Higher Ed institution",
            "canvas-usage": "Canvas is our LMS",
            "problem": "advising triage",
            "data-infra": "Developing",
        },
        "Our data is developing.",
    ),
    (
        5,
        {
            "org-type": "Higher Ed institution",
            "canvas-usage": "Canvas is our LMS",
            "problem": "advising triage",
            "data-infra": "Developing",
            "engineering": "Hybrid",
        },
        "We have hybrid engineering capacity.",
    ),
    (
        6,
        {
            "org-type": "Higher Ed institution",
            "canvas-usage": "Canvas is our LMS",
            "problem": "advising triage",
            "data-infra": "Developing",
            "engineering": "Hybrid",
            "timeline": "Exploring",
        },
        "We are still exploring.",
    ),
]


def _completed_intake(timeline: str) -> dict[str, str]:
    return {
        "org-type": "EdTech platform",
        "canvas-usage": "Canvas is a core integration target",
        "problem": "course content assistant",
        "data-infra": "Mature / clean",
        "engineering": "Internal team",
        "timeline": timeline,
        "success": "A usable pilot with measured support deflection",
    }


SCENARIOS: list[dict[str, Any]] = [
    *[
        {
            "name": f"open-{index}",
            "payload": _base_payload(question, session_id=f"matrix-open-{index}"),
            "mode": "open",
        }
        for index, question in enumerate(OPEN_QUESTIONS)
    ],
    *[
        {
            "name": f"about-{index}",
            "payload": _base_payload(
                question,
                mode="about",
                session_id=f"matrix-about-{index}",
            ),
            "mode": "about",
        }
        for index, question in enumerate(ABOUT_QUESTIONS)
    ],
    *[
        {
            "name": f"escalation-{index}",
            "payload": _base_payload(
                question,
                mode="open",
                session_id=f"matrix-escalation-{index}",
            ),
            "mode": "escalation",
            "escalate": expected,
        }
        for index, (question, expected) in enumerate(ESCALATION_QUESTIONS)
    ],
    *[
        {
            "name": f"intake-progress-{index}",
            "payload": _base_payload(
                content,
                mode="intake",
                session_id=f"matrix-intake-progress-{index}",
                intake_index=index,
                intake_answers=answers,
            ),
            "mode": "intake",
        }
        for index, answers, content in INTAKE_PROGRESS
    ],
    {
        "name": "intake-complete-high-intent-30-60",
        "payload": _base_payload(
            "Success is a production pilot.",
            mode="intake",
            session_id="matrix-intake-complete-high",
            intake_index=7,
            intake_answers=_completed_intake("30-60 days"),
        ),
        "mode": "intake",
        "snapshot": True,
        "escalate": "high_intent",
    },
    {
        "name": "intake-complete-high-intent-3-6",
        "payload": _base_payload(
            "Success is a deployable pilot.",
            mode="intake",
            session_id="matrix-intake-complete-three-six",
            intake_index=7,
            intake_answers=_completed_intake("3-6 months"),
        ),
        "mode": "intake",
        "snapshot": True,
        "escalate": "high_intent",
    },
    {
        "name": "intake-complete-exploring",
        "payload": _base_payload(
            "Success is clarity on whether to proceed.",
            mode="intake",
            session_id="matrix-intake-complete-exploring",
            intake_index=7,
            intake_answers=_completed_intake("Exploring"),
        ),
        "mode": "intake",
        "snapshot": True,
        "escalate": None,
    },
    {
        "name": "out-of-scope",
        "payload": _base_payload(
            "Can you recommend a backpacking route in Iceland?",
            session_id="matrix-out-of-scope",
        ),
        "mode": "open",
    },
]


def test_matrix_has_50_plus_representative_scenarios() -> None:
    assert len(SCENARIOS) >= 50


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[scenario["name"] for scenario in SCENARIOS])
def test_representative_conversation_matrix(scenario: dict[str, Any]) -> None:
    events = _post(scenario["payload"])

    assert events[0]["type"] == "phase"
    assert events[-1]["type"] == "done"
    assert [event["type"] for event in events].count("done") == 1
    assert not any(event.get("type") == "error" for event in events)

    if scenario["mode"] == "open" and "escalate" not in scenario:
        assert any(event["type"] == "token" for event in events)
    if scenario["mode"] == "about":
        assert all(event["type"] != "source" for event in events)
    if scenario["mode"] == "intake":
        assert events[0]["phase"] == "assessing"
    if "snapshot" in scenario:
        assert bool(events[-1]["snapshot"]) is scenario["snapshot"]
    if "escalate" in scenario:
        assert events[-1]["escalate"] == scenario["escalate"]

    text = "".join(event.get("token", "") for event in events)
    assert "I am human" not in text
    assert "I'm human" not in text


def test_confidence_escalates_after_two_low_confidence_turns() -> None:
    payload = _base_payload(
        "Can AI recommend a backpacking route in Iceland?",
        session_id="matrix-low-confidence-repeat",
    )

    first = _post(payload)
    second = _post(payload)

    assert first[-1]["escalate"] is None
    assert second[0:3] == [
        {"type": "phase", "phase": "searching"},
        {"type": "phase", "phase": "retrieving"},
        {"type": "phase", "phase": "escalating"},
    ]
    assert second[-1]["escalate"] == "confidence"
