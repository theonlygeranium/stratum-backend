from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from scripts.eval_deployed_conversations import _answer_substance_check
from scripts.conversation_scenarios import SCENARIOS, base_payload as _base_payload


client = TestClient(main_module.app)


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


def test_matrix_has_50_plus_representative_scenarios() -> None:
    assert len(SCENARIOS) >= 50


def test_deployed_eval_rejects_hollow_grounded_open_answer() -> None:
    scenario = {"name": "open-hollow", "mode": "open"}

    assert not _answer_substance_check(
        scenario,
        "Here is the grounded read: ",
        {"label": "Source", "score": 0.99, "grounded": True},
        [{"source": "Source", "excerpt": "supporting excerpt"}],
    )
    assert not _answer_substance_check(
        scenario,
        "This answer has enough words to look plausible, but no citation event support.",
        {"label": "Source", "score": 0.99, "grounded": True},
        [],
    )
    assert _answer_substance_check(
        scenario,
        (
            "This grounded answer contains enough substance to explain the visitor's "
            "question and is backed by at least one citation from the retrieved source."
        ),
        {"label": "Source", "score": 0.99, "grounded": True},
        [{"source": "Source", "excerpt": "supporting excerpt"}],
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[scenario["name"] for scenario in SCENARIOS])
def test_representative_conversation_matrix(scenario: dict[str, Any]) -> None:
    events = _post(scenario["payload"])

    assert events[0]["type"] == "phase"
    assert events[-1]["type"] == "done"
    assert [event["type"] for event in events].count("done") == 1
    assert not any(event.get("type") == "error" for event in events)

    if scenario["mode"] == "open" and "escalate" not in scenario:
        assert any(event["type"] == "token" for event in events)
        if scenario["name"] != "out-of-scope":
            source = next(event["source"] for event in events if event["type"] == "source")
            assert source["grounded"] is True
    if scenario["mode"] == "about":
        assert all(event["type"] != "source" for event in events)
        assert events[-1]["escalate"] is None
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
