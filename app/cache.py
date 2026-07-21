"""Short-lived semantic response cache for STRATUM."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    response: str
    source: dict[str, Any]
    citations: list[dict[str, Any]]
    timestamp: float


class SemanticCache:
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 100):
        self._store: dict[str, CacheEntry] = {}
        self._ttl = ttl_seconds
        self._max = max_entries

    def _key(self, query: str) -> str:
        normalized = query.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def get(self, query: str) -> CacheEntry | None:
        key = self._key(query)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() - entry.timestamp > self._ttl:
            del self._store[key]
            return None
        return entry

    def put(
        self,
        query: str,
        response: str,
        source: dict[str, Any],
        citations: list[dict[str, Any]],
    ) -> None:
        key = self._key(query)
        if len(self._store) >= self._max and key not in self._store:
            oldest = min(self._store, key=lambda item: self._store[item].timestamp)
            del self._store[oldest]
        self._store[key] = CacheEntry(response, source, citations, time.time())

    def invalidate(self) -> None:
        self._store.clear()
