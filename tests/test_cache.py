from __future__ import annotations

import time

from app.cache import SemanticCache


def test_semantic_cache_returns_and_expires_entries() -> None:
    cache = SemanticCache(ttl_seconds=1)
    cache.put(
        "What does EdStratum do?",
        "Cached response",
        {"label": "Source", "score": 1.0, "grounded": True},
        [{"source": "Source", "excerpt": "Evidence"}],
    )

    assert cache.get(" what does edstratum do? ") is not None
    entry = cache.get("What does EdStratum do?")
    assert entry is not None
    entry.timestamp = time.time() - 5
    assert cache.get("What does EdStratum do?") is None


def test_semantic_cache_evicts_oldest_entry() -> None:
    cache = SemanticCache(ttl_seconds=300, max_entries=1)
    cache.put("First", "one", {}, [])
    cache.put("Second", "two", {}, [])

    assert cache.get("First") is None
    assert cache.get("Second") is not None
