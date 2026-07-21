from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

from app.observability import increment_counter, log_event


class SessionStore:
    """Persist lightweight per-session STRATUM state when Postgres is available.

    The frontend sends full conversation history on each turn, so the backend
    only needs server-side continuity for counters and side-channel state. If
    Railway/Postgres credentials are absent or temporarily unavailable, the
    store degrades to memory without breaking the user-facing stream.
    """

    def __init__(self, database_url: str | None):
        self.database_url = database_url
        self.memory_counts: dict[str, int] = {}
        self._db_disabled = False
        self._db_retry_after = 0.0
        self._backoff_seconds = 5.0
        self._max_backoff = 300.0

    @property
    def backend_name(self) -> str:
        if self.database_url and self._should_retry_postgres():
            return "postgres"
        return "memory"

    @property
    def database_disabled(self) -> bool:
        return self._db_disabled

    async def get_low_confidence_count(self, session_id: str) -> int:
        state = await self.load_state(session_id)
        return int(state.get("low_confidence_count") or 0)

    async def set_low_confidence_count(self, session_id: str, count: int) -> None:
        state = await self.load_state(session_id)
        state["low_confidence_count"] = max(0, count)
        await self.save_state(session_id, state)

    async def increment_low_confidence_count(self, session_id: str) -> int:
        """Atomically increment and return the new low-confidence count."""
        if self.database_url and self._should_retry_postgres():
            try:
                count = await asyncio.to_thread(
                    self._increment_count_postgres,
                    session_id,
                )
                self.memory_counts[session_id] = count
                self._mark_postgres_available()
                return count
            except Exception as exc:
                self._mark_postgres_failed(exc)

        count = self.memory_counts.get(session_id, 0) + 1
        self.memory_counts[session_id] = count
        return count

    async def load_state(self, session_id: str) -> dict[str, Any]:
        if self.database_url and self._should_retry_postgres():
            try:
                state = await asyncio.to_thread(self._load_state_from_postgres, session_id)
                self._mark_postgres_available()
                return state
            except Exception as exc:
                self._mark_postgres_failed(exc)
        return {"low_confidence_count": self.memory_counts.get(session_id, 0)}

    async def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        count = int(state.get("low_confidence_count") or 0)
        self.memory_counts[session_id] = count

        if self.database_url and self._should_retry_postgres():
            try:
                await asyncio.to_thread(self._save_state_to_postgres, session_id, state)
                self._mark_postgres_available()
            except Exception as exc:
                self._mark_postgres_failed(exc)

    def _load_state_from_postgres(self, session_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT state_json FROM stratum_sessions WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        if not row:
            return {"low_confidence_count": self.memory_counts.get(session_id, 0)}
        data = json.loads(str(row[0]))
        return data if isinstance(data, dict) else {}

    def _save_state_to_postgres(self, session_id: str, state: dict[str, Any]) -> None:
        payload = dict(state)
        payload["updated_at"] = datetime.now(UTC).isoformat()
        serialized = json.dumps(payload, separators=(",", ":"))
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO stratum_sessions (session_id, state_json, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (session_id)
                DO UPDATE SET state_json = EXCLUDED.state_json, updated_at = NOW()
                """,
                (session_id, serialized),
            )

    def _increment_count_postgres(self, session_id: str) -> int:
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                """
                INSERT INTO stratum_sessions (session_id, state_json, updated_at)
                VALUES (%s, '{"low_confidence_count": 1}', NOW())
                ON CONFLICT (session_id)
                DO UPDATE SET
                    state_json = jsonb_set(
                        stratum_sessions.state_json::jsonb,
                        '{low_confidence_count}',
                        (
                            COALESCE(
                                (stratum_sessions.state_json::jsonb->>'low_confidence_count')::int,
                                0
                            ) + 1
                        )::text::jsonb
                    )::text,
                    updated_at = NOW()
                RETURNING (state_json::jsonb->>'low_confidence_count')::int
                """,
                (session_id,),
            ).fetchone()
        return int(row[0]) if row else 1

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, connect_timeout=2, autocommit=True)

    def _should_retry_postgres(self) -> bool:
        if not self._db_disabled:
            return True
        if time.time() >= self._db_retry_after:
            self._db_disabled = False
            return True
        return False

    def _mark_postgres_available(self) -> None:
        self._db_disabled = False
        self._db_retry_after = 0.0
        self._backoff_seconds = 5.0

    def _mark_postgres_failed(self, exc: Exception) -> None:
        self._db_disabled = True
        self._db_retry_after = time.time() + self._backoff_seconds
        self._backoff_seconds = min(self._backoff_seconds * 2, self._max_backoff)
        log_event(
            "error",
            "session_store_postgres_disabled",
            error_type=type(exc).__name__,
        )
        increment_counter("session_store_postgres_failures")

    @staticmethod
    def _ensure_schema(conn) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stratum_sessions (
                session_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
