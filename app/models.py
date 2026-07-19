from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


ProcessingPhase = Literal[
    "searching", "retrieving", "composing", "assessing", "escalating", "idle"
]
ConversationMode = Literal["open", "intake", "about", "escalation"]
EscalationTriggerValue = Literal["explicit", "confidence", "high_intent", "sentiment"]
EscalationTrigger: TypeAlias = EscalationTriggerValue | None


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceConfidence(ContractModel):
    label: str
    score: float = Field(ge=0.0, le=1.0)
    grounded: bool


class ReadinessSnapshot(ContractModel):
    situation: str
    capabilities: str
    firstStep: str


class ChatMessage(BaseModel):
    id: str | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: float | int
    phases: list[ProcessingPhase] | None = None
    source: SourceConfidence | None = None
    isIntakeQuestion: bool | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    messages: list[ChatMessage]
    mode: ConversationMode = "open"
    intake_index: int | None = Field(default=None, alias="intakeIndex")
    intake_answers: dict[str, str] = Field(default_factory=dict, alias="intakeAnswers")
    session_id: str = Field(alias="sessionId")


class StratumResult(ContractModel):
    phases: list[ProcessingPhase] = Field(min_length=1)
    source: SourceConfidence | None = None
    response_text: str
    snapshot: ReadinessSnapshot | None = None
    escalate: EscalationTrigger = None


class HealthResponse(ContractModel):
    status: Literal["healthy"] = "healthy"
    stratum: Literal["online"] = "online"
    backend_enabled: Literal[True] = True


class PhaseEvent(ContractModel):
    type: Literal["phase"]
    phase: ProcessingPhase


class TokenEvent(ContractModel):
    type: Literal["token"]
    token: str


class SourceEvent(ContractModel):
    type: Literal["source"]
    source: SourceConfidence


class DoneEvent(ContractModel):
    type: Literal["done"]
    snapshot: ReadinessSnapshot | None = None
    escalate: EscalationTrigger = None


class ErrorEvent(ContractModel):
    type: Literal["error"]
    message: str = Field(min_length=1)


StreamEvent: TypeAlias = Annotated[
    PhaseEvent | TokenEvent | SourceEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]
