from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agent import StratumAgent
from app.config import get_settings
from app.escalation import send_or_log_escalation
from app.models import (
    ChatRequest,
    ErrorEvent,
    EscalationDelivery,
    EscalationRequest,
    HealthResponse,
    RuntimeResponse,
    healthy_response,
)
from app.sse import sse_event

settings = get_settings()
agent = StratumAgent(settings)

REQUIRED_CORS_ORIGINS = [
    "https://edstratumlabs.ai",
    "https://www.edstratumlabs.ai",
    "https://edstratumlabs.pages.dev",
    "http://localhost:5173",
]

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _cors_origins(configured_origins: list[str]) -> list[str]:
    return list(dict.fromkeys([*REQUIRED_CORS_ORIGINS, *configured_origins]))


def _suppresses_notifications(request: Request) -> bool:
    return (
        request.headers.get("x-stratum-eval") == "true"
        or request.headers.get("x-stratum-qa") in {"true", "suppress-notifications"}
    )


app = FastAPI(
    title="STRATUM Backend",
    version="1.0.0",
    description="FastAPI/SSE backend for EdStratum Labs STRATUM.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(settings.allowed_origins),
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return healthy_response(rag_connected=bool(agent.retriever.docs))


@app.get("/api/runtime", response_model=RuntimeResponse)
async def runtime() -> RuntimeResponse:
    status = agent.runtime_status()
    status["required_cors_origins_present"] = all(
        origin in _cors_origins(settings.allowed_origins)
        for origin in REQUIRED_CORS_ORIGINS
    )
    return RuntimeResponse.model_validate(status)


@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request) -> StreamingResponse:
    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for event in agent.stream(
                request,
                suppress_notifications=_suppresses_notifications(http_request),
            ):
                yield sse_event(event)
        except Exception:
            yield sse_event(
                ErrorEvent(
                    type="error",
                    message=(
                        "STRATUM hit an internal error. The EdStratum team should review the backend logs."
                    ),
                )
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@app.post("/api/escalate", response_model=EscalationDelivery)
async def escalate(
    request: EscalationRequest,
    http_request: Request,
) -> EscalationDelivery:
    payload = {
        "conversation_transcript": "",
        "readiness_snapshot": {
            "situation": request.intake_summary.get("situation", "Not completed"),
            "capabilities": request.intake_summary.get("capabilities", "Not completed"),
            "firstStep": request.intake_summary.get("firstStep", "Not completed"),
        },
        "intent_category": "escalation",
        "key_signals": request.intake_summary,
        "escalation_trigger": request.escalation_reason,
        "visitor_contact": {
            "name": request.lead_name,
            "email": request.lead_email,
            "phone": None,
        },
        "session_id": request.session_id,
        "timestamp": request.timestamp or datetime.now(UTC).isoformat(),
    }
    return await send_or_log_escalation(
        settings,
        payload,
        suppress_notifications=_suppresses_notifications(http_request),
    )
