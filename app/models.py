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


class RagCitation(ContractModel):
    source: str
    excerpt: str = Field(min_length=1)


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
    citations: list[RagCitation] | None = None
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
    citations: list[RagCitation] = Field(default_factory=list)
    response_text: str
    snapshot: ReadinessSnapshot | None = None
    escalate: EscalationTrigger = None


class RagHealth(ContractModel):
    status: Literal["ok", "degraded"]
    vectorStoreConnected: bool


class HealthResponse(ContractModel):
    status: Literal["healthy"] = "healthy"
    stratum: Literal["online"] = "online"
    backend_enabled: Literal[True] = True
    rag: RagHealth


def healthy_response(*, rag_connected: bool) -> HealthResponse:
    return HealthResponse(
        rag=RagHealth(
            status="ok" if rag_connected else "degraded",
            vectorStoreConnected=rag_connected,
        )
    )


class RuntimeResponse(ContractModel):
    status: Literal["online"] = "online"
    graph_runtime: Literal["langgraph", "procedural"]
    checkpointer: Literal["uninitialized", "memory", "postgres", "none"]
    database_configured: bool
    session_store_backend: Literal["postgres", "memory"]
    session_store_database_disabled: bool
    embedding_provider: str
    vector_store_provider: str
    reranker_provider: str
    reranker_model: str | None = None
    llm_configured: bool
    llm_provider: str
    llm_base_url: str
    llm_model: str
    writer_api_key_configured: bool
    openai_api_key_configured: bool
    resend_configured: bool
    escalation_email_configured: bool
    notifications_configured: bool
    allowed_origins_env_configured: bool
    required_cors_origins_present: bool


class PhaseEvent(ContractModel):
    type: Literal["phase"]
    phase: ProcessingPhase


class TokenEvent(ContractModel):
    type: Literal["token"]
    token: str


class SourceEvent(ContractModel):
    type: Literal["source"]
    source: SourceConfidence


class CitationsEvent(ContractModel):
    type: Literal["citations"]
    data: list[RagCitation]


class DoneEvent(ContractModel):
    type: Literal["done"]
    snapshot: ReadinessSnapshot | None = None
    escalate: EscalationTrigger = None


class ErrorEvent(ContractModel):
    type: Literal["error"]
    message: str = Field(min_length=1)


StreamEvent: TypeAlias = Annotated[
    PhaseEvent | TokenEvent | SourceEvent | CitationsEvent | DoneEvent | ErrorEvent,
    Field(discriminator="type"),
]
