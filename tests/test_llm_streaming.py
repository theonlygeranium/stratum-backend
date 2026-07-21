from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.agent import _truncate_response
from app.config import Settings
from app.llm import build_chat_messages, stream_response


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
        pinecone_api_key=None,
        pinecone_index=None,
        pinecone_namespace=None,
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
        elevenlabs_base_url="https://api.us.elevenlabs.io/v1",
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
    assert captured["json"]["max_tokens"] == 200
    assert captured["json"]["messages"][0] == {"role": "system", "content": "system"}


def test_truncate_response_prefers_sentence_boundary() -> None:
    response = (
        "First sentence is useful. Second sentence should stay intact. "
        "Third sentence is too long for the configured response budget."
    )

    truncated = _truncate_response(response, 70)

    assert truncated == "First sentence is useful. Second sentence should stay intact.…"
    assert len(truncated) < len(response)


def test_build_chat_messages_summarizes_older_history(monkeypatch) -> None:
    captured: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Visitor has Canvas data questions and wants a maintainable pilot."
                        }
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict):
            captured.append(json)
            return FakeResponse()

    monkeypatch.setattr("app.llm.httpx.AsyncClient", FakeAsyncClient)
    settings = _settings()
    object.__setattr__(settings, "llm_history_window", 2)
    object.__setattr__(settings, "llm_summary_threshold", 3)
    history = [
        {"role": "user", "content": f"user turn {index}"}
        if index % 2 == 0
        else {"role": "assistant", "content": f"assistant turn {index}"}
        for index in range(6)
    ]

    messages = asyncio.run(
        build_chat_messages(
            settings=settings,
            system_prompt="system",
            context="context",
            conversation_history=history,
            query="query",
        )
    )

    assert captured
    assert messages[1]["role"] == "system"
    assert "Conversation summary so far" in messages[1]["content"]
    assert [message["content"] for message in messages[2:4]] == [
        "user turn 4",
        "assistant turn 5",
    ]


def test_build_chat_messages_drops_old_history_when_summary_fails(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict):
            raise RuntimeError("summary down")

    monkeypatch.setattr("app.llm.httpx.AsyncClient", FakeAsyncClient)
    settings = _settings()
    object.__setattr__(settings, "llm_history_window", 2)
    object.__setattr__(settings, "llm_summary_threshold", 3)
    history = [{"role": "user", "content": f"turn {index}"} for index in range(5)]

    messages = asyncio.run(
        build_chat_messages(
            settings=settings,
            system_prompt="system",
            context="context",
            conversation_history=history,
            query="query",
        )
    )

    assert [message["content"] for message in messages[1:3]] == ["turn 3", "turn 4"]
    assert all(
        "Conversation summary so far" not in message["content"] for message in messages
    )
