from __future__ import annotations

import pytest

from scripts import live_release_audit


def clear_expectation_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in live_release_audit.FRONTEND_FLAG_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    for env_name in live_release_audit.BACKEND_RUNTIME_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.delenv(live_release_audit.BACKEND_TTS_STATUS_ENV, raising=False)


def test_release_audit_expectations_default_to_current_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_expectation_env(monkeypatch)

    args = live_release_audit.parse_args(["--skip-github"])

    assert args.expectations == live_release_audit.RuntimeExpectations(
        frontend_flags={
            "ragEnabled": True,
            "voiceEnabled": False,
            "persistenceEnabled": False,
        },
        backend_runtime={
            "graph_runtime": "langgraph",
            "session_store_backend": "postgres",
            "embedding_provider": "hash",
            "vector_store_provider": "chroma",
            "llm_provider": "writer",
        },
        backend_tts_status="unconfigured",
    )


def test_release_audit_expectation_cli_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_expectation_env(monkeypatch)
    monkeypatch.setenv("STRATUM_AUDIT_EXPECT_VOICE_ENABLED", "true")
    monkeypatch.setenv("STRATUM_AUDIT_EXPECT_EMBEDDING_PROVIDER", "hash")

    args = live_release_audit.parse_args(
        [
            "--skip-github",
            "--expected-voice-enabled",
            "false",
            "--expected-embedding-provider",
            "openai",
            "--expected-vector-store-provider",
            "pinecone",
            "--expected-tts-status",
            "ok",
        ]
    )

    assert args.expectations.frontend_flags["voiceEnabled"] is False
    assert args.expectations.backend_runtime["embedding_provider"] == "openai"
    assert args.expectations.backend_runtime["vector_store_provider"] == "pinecone"
    assert args.expectations.backend_tts_status == "ok"


def test_release_audit_rejects_unsafe_provider_expectations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear_expectation_env(monkeypatch)

    with pytest.raises(SystemExit):
        live_release_audit.parse_args(
            ["--skip-github", "--expected-embedding-provider", "sk-test-secret"]
        )

    captured = capsys.readouterr()
    assert "sk-test-secret" not in captured.err
    assert "embedding_provider must be one of" in captured.err


def test_frontend_public_audit_uses_configured_flag_expectations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_json(
        url: str,
        timeout: float = 15.0,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object], dict[str, str]]:
        if "build-manifest.json" in url:
            return (
                200,
                {
                    "commitShortSha": "abc1234",
                    "commitSha": "abc1234def",
                    "backendUrl": live_release_audit.DEFAULT_BACKEND_URL,
                    "assets": [f"/assets/{index}.js" for index in range(5)],
                },
                {"cache-control": "public, max-age=60, must-revalidate"},
            )
        if url.endswith("/api/config"):
            return (
                200,
                {
                    "ragEnabled": True,
                    "voiceEnabled": True,
                    "persistenceEnabled": True,
                },
                {},
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(live_release_audit, "fetch_json", fake_fetch_json)
    audit = live_release_audit.Audit()
    expectations = live_release_audit.RuntimeExpectations(
        frontend_flags={
            "ragEnabled": True,
            "voiceEnabled": True,
            "persistenceEnabled": True,
        },
        backend_runtime=dict(live_release_audit.DEFAULT_BACKEND_RUNTIME),
        backend_tts_status=live_release_audit.DEFAULT_BACKEND_TTS_STATUS,
    )

    live_release_audit.inspect_frontend_public(
        audit,
        live_release_audit.DEFAULT_FRONTEND_URL,
        "abc1234def",
        live_release_audit.DEFAULT_BACKEND_URL,
        expectations,
    )

    assert audit.blockers == 0
    assert any(
        record.name == "frontend runtime flag voiceEnabled" and record.detail == "true"
        for record in audit.records
    )


def test_backend_public_audit_uses_configured_provider_expectations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fetch_json(
        url: str,
        timeout: float = 15.0,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object], dict[str, str]]:
        if url.endswith("/api/health"):
            return (
                200,
                {
                    "status": "healthy",
                    "backend_enabled": True,
                    "rag": {"status": "ok", "vectorStoreConnected": True},
                    "tts": {"status": "ok", "provider": "elevenlabs"},
                },
                {"access-control-allow-origin": live_release_audit.DEFAULT_FRONTEND_URL},
            )
        if url.endswith("/api/runtime"):
            return (
                200,
                {
                    "status": "online",
                    "graph_runtime": "langgraph",
                    "session_store_backend": "postgres",
                    "embedding_provider": "openai",
                    "vector_store_provider": "pinecone",
                    "llm_provider": "writer",
                    "database_configured": True,
                    "llm_configured": True,
                    "notifications_configured": True,
                    "required_cors_origins_present": True,
                },
                {},
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(live_release_audit, "fetch_json", fake_fetch_json)
    audit = live_release_audit.Audit()
    backend_runtime = dict(live_release_audit.DEFAULT_BACKEND_RUNTIME)
    backend_runtime["embedding_provider"] = "openai"
    backend_runtime["vector_store_provider"] = "pinecone"
    expectations = live_release_audit.RuntimeExpectations(
        frontend_flags=dict(live_release_audit.DEFAULT_FRONTEND_FLAGS),
        backend_runtime=backend_runtime,
        backend_tts_status="ok",
    )

    live_release_audit.inspect_backend_public(
        audit,
        live_release_audit.DEFAULT_BACKEND_URL,
        expectations,
    )

    assert audit.blockers == 0
    assert audit.warnings == 0
    assert any(
        record.name == "backend runtime vector_store_provider"
        and record.detail == "pinecone"
        for record in audit.records
    )
