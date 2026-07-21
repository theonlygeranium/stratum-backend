from __future__ import annotations

from app.scope_guard import is_likely_in_scope


def test_scope_guard_accepts_service_area_queries() -> None:
    assert is_likely_in_scope("Can you help with Canvas LTI grade passback?")
    assert is_likely_in_scope("How should we improve RAG retrieval confidence?")
    assert is_likely_in_scope("We need an AI implementation strategy roadmap.")


def test_scope_guard_accepts_general_intake_queries() -> None:
    assert is_likely_in_scope("What does EdStratum do?")
    assert is_likely_in_scope("How do I contact the Founding leadership team?")


def test_scope_guard_rejects_unrelated_queries() -> None:
    assert not is_likely_in_scope("What is the best backpacking route in Iceland?")
    assert not is_likely_in_scope("Can you plan a dinner menu for next week?")
