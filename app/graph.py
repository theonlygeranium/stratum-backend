from __future__ import annotations

from typing import Annotated, Any, TypedDict, cast

from app.models import (
    ChatMessage,
    ChatRequest,
    ConversationMode,
    EscalationTrigger,
    ReadinessSnapshot,
    SourceConfidence,
)


try:
    from langgraph.graph.message import add_messages
except Exception:  # pragma: no cover - optional dependency fallback
    def add_messages(left, right):
        return [*(left or []), *(right or [])]


class StratumState(TypedDict):
    messages: Annotated[list[ChatMessage], add_messages]
    mode: ConversationMode
    intake_index: int | None
    intake_answers: dict[str, str]
    retrieved_context: list
    source_confidence: SourceConfidence | None
    escalation_trigger: EscalationTrigger
    escalation_context: dict[str, Any] | None
    response_text: str
    snapshot: ReadinessSnapshot | None
    session_id: str


VALID_ROUTE_KEYS: set[ConversationMode] = {"open", "intake", "about", "escalation"}


def initial_state_from_request(request: ChatRequest) -> StratumState:
    return {
        "messages": request.messages,
        "mode": request.mode,
        "intake_index": request.intake_index,
        "intake_answers": request.intake_answers,
        "retrieved_context": [],
        "source_confidence": None,
        "escalation_trigger": None,
        "escalation_context": None,
        "response_text": "",
        "snapshot": None,
        "session_id": request.session_id,
    }


def route_key(state: StratumState) -> ConversationMode:
    mode = state.get("mode") or "open"
    if mode not in VALID_ROUTE_KEYS:
        return "open"
    return cast(ConversationMode, mode)
