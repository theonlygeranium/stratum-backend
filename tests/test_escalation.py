from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import Settings
from app.escalation import (
    RESEND_FALLBACK_FROM_EMAIL,
    _ESCALATION_SENDS,
    send_or_log_escalation,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        allowed_origins=[],
        confidence_threshold=0.55,
        calendly_url="https://calendly.example",
        knowledge_base_dir=Path("data/knowledge_base"),
        escalation_log_dir=tmp_path,
        database_url=None,
        embedding_provider="hash",
        embedding_model="text-embedding-3-small",
        vector_store_provider="chroma",
        chroma_persist_dir=None,
        reranker_provider="heuristic",
        reranker_model="rerank-v4.0-fast",
        openai_api_key=None,
        writer_api_key=None,
        cohere_api_key=None,
        llm_api_key=None,
        llm_provider="writer",
        llm_base_url="https://llm.example/v1/chat/completions",
        llm_model="gpt-4o",
        resend_api_key="test-resend-key",
        jeffrey_email="jeffrey@example.com",
        resend_from_email="stratum@example.com",
    )


def test_resend_sender_falls_back_to_default_sender(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, ok: bool):
            self.ok = ok

        def raise_for_status(self) -> None:
            if not self.ok:
                raise RuntimeError("sender rejected")

        def json(self) -> dict:
            return {"id": "resend-123"}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict):
            del url, headers
            calls.append(json["from"])
            return FakeResponse(ok=json["from"] == RESEND_FALLBACK_FROM_EMAIL)

    monkeypatch.setattr("app.escalation.httpx.AsyncClient", FakeClient)

    result = asyncio.run(
        send_or_log_escalation(
            _settings(tmp_path),
            {
                "conversation_transcript": "USER: hello",
                "readiness_snapshot": None,
                "intent_category": "open",
                "key_signals": {},
                "escalation_trigger": "explicit",
                "visitor_contact": {"email": None, "phone": None},
                "session_id": "resend-fallback",
                "timestamp": "2026-07-20T00:00:00+00:00",
            },
        )
    )

    assert result.success is True
    assert result.status == "sent"
    assert result.messageId == "resend-123"
    assert calls == ["stratum@example.com", RESEND_FALLBACK_FROM_EMAIL]
    assert (tmp_path / "resend-fallback.json").exists()


def test_qa_suppression_skips_resend_call(monkeypatch, tmp_path) -> None:
    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            raise AssertionError("QA suppression must not create an HTTP client")

    monkeypatch.setattr("app.escalation.httpx.AsyncClient", FakeClient)

    result = asyncio.run(
        send_or_log_escalation(
            _settings(tmp_path),
            {
                "conversation_transcript": "USER: hello",
                "readiness_snapshot": None,
                "intent_category": "open",
                "key_signals": {},
                "escalation_trigger": "explicit",
                "visitor_contact": {"email": None, "phone": None},
                "session_id": "qa-suppressed",
                "timestamp": "2026-07-20T00:00:00+00:00",
            },
            suppress_notifications=True,
        )
    )

    assert result.success is True
    assert result.status == "suppressed"
    assert result.messageId == "qa-suppressed"


def test_escalation_rate_limit_is_per_session(monkeypatch, tmp_path) -> None:
    calls = 0
    _ESCALATION_SENDS.clear()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "resend-rate"}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeResponse()

    monkeypatch.setattr("app.escalation.httpx.AsyncClient", FakeClient)
    settings = _settings(tmp_path)
    payload = {
        "conversation_transcript": "USER: hello",
        "readiness_snapshot": None,
        "intent_category": "open",
        "key_signals": {},
        "escalation_trigger": "explicit",
        "visitor_contact": {"email": None, "phone": None},
        "session_id": "rate-limited-session",
        "timestamp": "2026-07-20T00:00:00+00:00",
    }

    results = [
        asyncio.run(send_or_log_escalation(settings, payload))
        for _ in range(4)
    ]

    assert [result.status for result in results] == [
        "sent",
        "sent",
        "sent",
        "rate_limited",
    ]
    assert calls == 3
