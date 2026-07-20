from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any


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

    @property
    def backend_name(self) -> str:
        if self.database_url and not self._db_disabled:
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

    async def load_state(self, session_id: str) -> dict[str, Any]:
        if self.database_url and not self._db_disabled:
            try:
                return await asyncio.to_thread(self._load_state_from_postgres, session_id)
            except Exception:
                self._db_disabled = True
        return {"low_confidence_count": self.memory_counts.get(session_id, 0)}

    async def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        count = int(state.get("low_confidence_count") or 0)
        self.memory_counts[session_id] = count

        if self.database_url and not self._db_disabled:
            try:
                await asyncio.to_thread(self._save_state_to_postgres, session_id, state)
            except Exception:
                self._db_disabled = True

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

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, connect_timeout=2, autocommit=True)

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
