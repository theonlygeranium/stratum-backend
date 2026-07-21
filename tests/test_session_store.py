from __future__ import annotations

import asyncio

from app.session_store import SessionStore


def test_memory_low_confidence_increment_handles_concurrent_calls() -> None:
    store = SessionStore(database_url=None)

    async def increment_many() -> list[int]:
        return await asyncio.gather(
            *(store.increment_low_confidence_count("concurrent") for _ in range(25))
        )

    results = asyncio.run(increment_many())

    assert sorted(results) == list(range(1, 26))
    assert store.memory_counts["concurrent"] == 25


def test_postgres_retry_after_transient_failure(monkeypatch) -> None:
    store = SessionStore(database_url="postgresql://example/stratum")
    calls = 0

    def fake_load(session_id: str) -> dict[str, int]:
        nonlocal calls
        assert session_id == "retry-session"
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        return {"low_confidence_count": 7}

    monkeypatch.setattr(store, "_load_state_from_postgres", fake_load)

    first = asyncio.run(store.load_state("retry-session"))
    store._db_retry_after = 0
    second = asyncio.run(store.load_state("retry-session"))

    assert first == {"low_confidence_count": 0}
    assert second == {"low_confidence_count": 7}
    assert store.database_disabled is False
    assert calls == 2
