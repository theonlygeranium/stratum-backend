from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.tts import _TTS_REQUESTS

client = TestClient(main_module.app)


def setup_function() -> None:
    _TTS_REQUESTS.clear()
    object.__setattr__(main_module.settings, "elevenlabs_api_key", None)
    object.__setattr__(main_module.settings, "elevenlabs_voice_id", "default-voice")


def test_tts_returns_503_when_provider_not_configured() -> None:
    response = client.post(
        "/api/tts",
        json={"text": "Hello from STRATUM."},
        headers={"X-Stratum-Session": "tts-unconfigured"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "tts_not_configured"


def test_tts_rejects_messages_over_500_characters() -> None:
    object.__setattr__(main_module.settings, "elevenlabs_api_key", "test-key")

    response = client.post(
        "/api/tts",
        json={"text": "x" * 501},
        headers={"X-Stratum-Session": "tts-too-long"},
    )

    assert response.status_code == 422


def test_tts_proxies_text_to_elevenlabs(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"mp3-bytes"
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, params: dict, headers: dict, json: dict):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.tts.httpx.AsyncClient", FakeClient)
    object.__setattr__(main_module.settings, "elevenlabs_api_key", "test-key")

    response = client.post(
        "/api/tts",
        json={"text": "Hello from STRATUM.", "voiceId": "voice-override"},
        headers={"X-Stratum-Session": "tts-proxy"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"mp3-bytes"
    assert captured["url"].endswith("/v1/text-to-speech/voice-override")
    assert captured["params"] == {"output_format": "mp3_44100_128"}
    assert captured["headers"]["xi-api-key"] == "test-key"
    assert captured["headers"]["Accept"] == "audio/mpeg"
    assert captured["json"] == {
        "text": "Hello from STRATUM.",
        "model_id": "eleven_multilingual_v2",
    }


def test_tts_rate_limit_is_per_session(monkeypatch) -> None:
    calls = 0

    class FakeResponse:
        status_code = 200
        content = b"mp3-bytes"
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            return FakeResponse()

    monkeypatch.setattr("app.tts.httpx.AsyncClient", FakeClient)
    object.__setattr__(main_module.settings, "elevenlabs_api_key", "test-key")

    responses = [
        client.post(
            "/tts",
            json={"text": "Hello from STRATUM."},
            headers={"X-Stratum-Session": "same-session"},
        )
        for _ in range(11)
    ]

    assert [response.status_code for response in responses[:10]] == [200] * 10
    assert responses[-1].status_code == 429
    assert responses[-1].json()["detail"] == "tts_rate_limited"
    assert calls == 10
