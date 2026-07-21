from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.agent import StratumAgent
from app.config import get_settings
from app.escalation import send_or_log_escalation
from app.models import (
    ChatRequest,
    DoneEvent,
    ErrorEvent,
    EscalationDelivery,
    EscalationRequest,
    HealthResponse,
    RuntimeResponse,
    StreamEvent,
    TTSRequest,
    healthy_response,
)
from app.observability import render_prometheus_metrics
from app.sse import sse_event
from app.tts import synthesize_speech

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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    try:
        yield
    finally:
        await agent.close()


app = FastAPI(
    title="STRATUM Backend",
    version="1.0.0",
    description="FastAPI/SSE backend for EdStratum Labs STRATUM.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(settings.allowed_origins),
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return healthy_response(
        rag_connected=bool(agent.retriever.docs),
        tts_configured=bool(settings.elevenlabs_api_key),
    )


@app.get("/api/runtime", response_model=RuntimeResponse)
async def runtime() -> RuntimeResponse:
    status = agent.runtime_status()
    status["required_cors_origins_present"] = all(
        origin in _cors_origins(settings.allowed_origins)
        for origin in REQUIRED_CORS_ORIGINS
    )
    return RuntimeResponse.model_validate(status)


@app.get("/api/metrics")
async def metrics() -> Response:
    if not settings.enable_metrics:
        return Response(status_code=404)
    return Response(
        content=render_prometheus_metrics(),
        media_type="text/plain; version=0.0.4",
    )


@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request) -> StreamingResponse:
    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for item in _stream_with_keepalive(
                agent.stream(
                    request,
                    suppress_notifications=_suppresses_notifications(http_request),
                )
            ):
                yield item
        except Exception:
            yield sse_event(
                ErrorEvent(
                    type="error",
                    message=(
                        "STRATUM hit an internal error. The EdStratum team should review the backend logs."
                    ),
                )
            )
            yield sse_event(DoneEvent(type="done"))

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _stream_with_keepalive(
    events: AsyncGenerator[StreamEvent, None],
    *,
    interval_s: float = 10.0,
) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def producer() -> None:
        try:
            async for event in events:
                await queue.put(sse_event(event))
        finally:
            await queue.put(None)

    async def keepalive() -> None:
        while True:
            await asyncio.sleep(interval_s)
            await queue.put(":keepalive\n\n")

    producer_task = asyncio.create_task(producer())
    keepalive_task = asyncio.create_task(keepalive())

    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    finally:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        await producer_task


@app.post("/api/escalate", response_model=EscalationDelivery)
async def escalate(
    request: EscalationRequest,
    http_request: Request,
) -> EscalationDelivery | JSONResponse:
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
    delivery = await send_or_log_escalation(
        settings,
        payload,
        suppress_notifications=_suppresses_notifications(http_request),
    )
    if not delivery.success and delivery.status != "suppressed":
        return JSONResponse(
            status_code=500,
            content=delivery.model_dump(by_alias=True),
        )

    return delivery


def _tts_session_key(request: Request) -> str:
    header_session = request.headers.get("x-stratum-session")
    if header_session:
        return header_session

    return request.client.host if request.client else "anonymous"


@app.post("/api/tts")
@app.post("/tts")
async def tts(request: TTSRequest, http_request: Request) -> StreamingResponse:
    audio_stream, content_type = await synthesize_speech(
        settings,
        request,
        session_key=_tts_session_key(http_request),
    )
    return StreamingResponse(
        audio_stream,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )
