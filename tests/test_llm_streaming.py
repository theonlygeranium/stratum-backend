from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.config import Settings
from app.llm import stream_response


def _settings() -> Settings:
    return Settings(
        allowed_origins=[],
        confidence_threshold=0.55,
        calendly_url="https://calendly.example",
        knowledge_base_dir=Path("data/knowledge_base"),
        escalation_log_dir=Path("data/escalations"),
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
        llm_api_key="test-key",
        llm_provider="writer",
        llm_base_url="https://llm.example/v1/chat/completions",
        llm_model="gpt-4o",
        resend_api_key=None,
        jeffrey_email=None,
        resend_from_email="stratum@example.com",
        elevenlabs_api_key=None,
        elevenlabs_voice_id="test-voice",
    )


def test_stream_response_parses_openai_compatible_deltas(monkeypatch) -> None:
    captured = {}

    class FakeStreamResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_lines(self):
            for payload in [
                {"choices": [{"delta": {"content": "Hello"}}]},
                {"choices": [{"delta": {"content": " there"}}]},
            ]:
                yield f"data: {json.dumps(payload)}"
            yield "data: [DONE]"

    class FakeStreamContext:
        async def __aenter__(self):
            return FakeStreamResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(self, method: str, url: str, *, headers: dict, json: dict):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeStreamContext()

    monkeypatch.setattr("app.llm.httpx.AsyncClient", FakeAsyncClient)

    async def collect_tokens() -> list[str]:
        return [
            token
            async for token in stream_response(
                _settings(),
                "system",
                "context",
                [{"role": "user", "content": "earlier"}],
                "query",
            )
        ]

    tokens = asyncio.run(collect_tokens())

    assert tokens == ["Hello", " there"]
    assert captured["method"] == "POST"
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["json"]["stream"] is True
    assert captured["json"]["messages"][0] == {"role": "system", "content": "system"}
