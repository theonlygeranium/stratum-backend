from __future__ import annotations

from collections.abc import AsyncIterator
from collections import defaultdict, deque
from time import monotonic
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.config import Settings
from app.models import TTSRequest

# ElevenLabs model — eleven_flash_v2_5 is the lowest-latency model, ported from
# Project-Tango where it was validated across six production personas. The
# previous eleven_multilingual_v2 model adds ~200ms latency with no quality
# benefit for English-only EdStratum responses.
ELEVENLABS_MODEL_ID = "eleven_flash_v2_5"

# Voice settings ported from Project-Tango's "general-info" persona, which
# produced the most natural professional delivery. These values were
# validated in production across hundreds of conversations.
#   stability: 0.60 — moderate; allows natural expressiveness without drift
#   similarity_boost: 0.80 — high; keeps the voice consistent
#   style: 0.15 — slight; adds conversational naturalness
#   use_speaker_boost: False — disabled across all Project-Tango personas
ELEVENLABS_VOICE_SETTINGS = {
    "stability": 0.60,
    "similarity_boost": 0.80,
    "style": 0.15,
    "use_speaker_boost": False,
}

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
) -> tuple[AsyncIterator[bytes], str]:
    if not settings.elevenlabs_api_key:
        raise HTTPException(status_code=503, detail="tts_not_configured")

    _check_rate_limit(session_key)

    voice_id = (request.voice_id or settings.elevenlabs_voice_id).strip()
    if not voice_id:
        raise HTTPException(status_code=503, detail="tts_voice_not_configured")

    # Use the configurable base URL (defaults to the US regional endpoint for
    # lower latency, ported from Project-Tango).
    base_url = settings.elevenlabs_base_url.rstrip("/")
    url = f"{base_url}/text-to-speech/{quote(voice_id, safe='')}"

    client = httpx.AsyncClient(timeout=30.0)
    upstream_request = client.build_request(
        "POST",
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
            "voice_settings": ELEVENLABS_VOICE_SETTINGS,
        },
    )

    try:
        response = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="tts_provider_error") from exc

    if response.status_code >= 400:
        await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail="tts_provider_error")

    async def audio_chunks() -> AsyncIterator[bytes]:
        try:
            async for chunk in response.aiter_bytes():
                if chunk:
                    yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return audio_chunks(), response.headers.get("content-type", "audio/mpeg")
