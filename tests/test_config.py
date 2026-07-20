from __future__ import annotations

from app.config import get_settings


def test_provider_defaults_use_deterministic_fallbacks_without_keys(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("RERANKER_PROVIDER", raising=False)

    settings = get_settings()

    assert settings.embedding_provider == "hash"
    assert settings.reranker_provider == "heuristic"


def test_provider_defaults_select_production_services_when_keys_exist(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("RERANKER_PROVIDER", raising=False)

    settings = get_settings()

    assert settings.embedding_provider == "openai"
    assert settings.reranker_provider == "cohere"
    assert settings.cohere_api_key == "test-cohere-key"


def test_explicit_provider_env_overrides_auto_defaults(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("RERANKER_PROVIDER", "heuristic")

    settings = get_settings()

    assert settings.embedding_provider == "hash"
    assert settings.reranker_provider == "heuristic"
