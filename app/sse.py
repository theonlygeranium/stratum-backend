from __future__ import annotations

import json
import re
from collections.abc import Iterable

from pydantic import TypeAdapter

from app.models import (
    DoneEvent,
    PhaseEvent,
    SourceEvent,
    StratumResult,
    StreamEvent,
    TokenEvent,
)

_STREAM_EVENT_ADAPTER = TypeAdapter(StreamEvent)


def sse_event(payload: StreamEvent | dict) -> str:
    event = _STREAM_EVENT_ADAPTER.validate_python(payload)
    data = event.model_dump(mode="json", by_alias=True)
    return f"data: {json.dumps(data, separators=(',', ':'))}\n\n"


def stream_events(result: StratumResult) -> Iterable[StreamEvent]:
    for phase in result.phases:
        yield PhaseEvent(type="phase", phase=phase)
    if result.source is not None:
        yield SourceEvent(type="source", source=result.source)
    for token in token_chunks(result.response_text):
        yield TokenEvent(type="token", token=token)
    yield DoneEvent(type="done", snapshot=result.snapshot, escalate=result.escalate)


def token_chunks(text: str) -> Iterable[str]:
    for match in re.finditer(r"\S+\s*", text):
        yield match.group(0)
