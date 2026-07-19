from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agent import StratumAgent
from app.config import get_settings
from app.models import ChatRequest, ErrorEvent, HealthResponse
from app.sse import sse_event, stream_events

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
    return HealthResponse()


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    async def stream() -> AsyncGenerator[str, None]:
        try:
            result = await agent.respond(request)
            for event in stream_events(result):
                yield sse_event(event)
        except Exception:
            yield sse_event(
                ErrorEvent(
                    type="error",
                    message=(
                        "STRATUM hit an internal error. Jeffrey should review the backend logs."
                    ),
                )
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
