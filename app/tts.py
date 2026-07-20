from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.config import Settings
from app.models import TTSRequest

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
TTS_RATE_LIMIT = 10
TTS_RATE_LIMIT_WINDOW_SECONDS = 60.0

_TTS_REQUESTS: dict[str, deque[float]] = defaultdict(deque)


def _check_rate_limit(session_key: str) -> None:
    now = monotonic()
    bucket = _TTS_REQUESTS[session_key]

    while bucket and now - bucket[0] >= TTS_RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()

    if len(bucket) >= TTS_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="tts_rate_limited")

    bucket.append(now)


async def synthesize_speech(
    settings: Settings,
    request: TTSRequest,
    *,
    session_key: str,
) -> tuple[bytes, str]:
    if not settings.elevenlabs_api_key:
        raise HTTPException(status_code=503, detail="tts_not_configured")

    _check_rate_limit(session_key)

    voice_id = (request.voice_id or settings.elevenlabs_voice_id).strip()
    if not voice_id:
        raise HTTPException(status_code=503, detail="tts_voice_not_configured")

    url = ELEVENLABS_TTS_URL.format(voice_id=quote(voice_id, safe=""))
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            params={"output_format": "mp3_44100_128"},
            headers={
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": settings.elevenlabs_api_key,
            },
            json={
                "text": request.text,
                "model_id": ELEVENLABS_MODEL_ID,
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="tts_provider_error")

    return response.content, response.headers.get("content-type", "audio/mpeg")
