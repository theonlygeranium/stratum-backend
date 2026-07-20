from __future__ import annotations

from app.config import get_settings
from app.rag.vector_store import HashEmbeddingProvider, build_embedding_provider


def test_provider_defaults_use_deterministic_fallbacks_without_keys(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WRITER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("RERANKER_PROVIDER", raising=False)

    settings = get_settings()

    assert settings.llm_provider == "writer"
    assert settings.llm_base_url == "https://api.writer.com/v1/chat/completions"
    assert settings.llm_model == "palmyra-x5"
    assert settings.llm_api_key is None
    assert settings.embedding_provider == "hash"
    assert settings.reranker_provider == "heuristic"


def test_writer_api_key_is_preferred_for_generation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("WRITER_API_KEY", "test-writer-key")
    monkeypatch.setenv("LLM_API_KEY", "test-llm-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("RERANKER_PROVIDER", raising=False)

    settings = get_settings()

    assert settings.llm_provider == "writer"
    assert settings.llm_api_key == "test-writer-key"
    assert settings.writer_api_key == "test-writer-key"
    assert settings.llm_model == "palmyra-x5"
    assert settings.embedding_provider == "hash"
    assert settings.openai_api_key == "test-openai-key"
    assert settings.reranker_provider == "cohere"
    assert settings.cohere_api_key == "test-cohere-key"


def test_openai_generation_requires_explicit_openai_provider(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("WRITER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    settings = get_settings()

    assert settings.llm_provider == "writer"
    assert settings.llm_api_key is None
    assert settings.embedding_provider == "hash"
    assert settings.openai_api_key == "test-openai-key"

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    openai_settings = get_settings()

    assert openai_settings.llm_provider == "openai"
    assert openai_settings.llm_base_url == "https://api.openai.com/v1/chat/completions"
    assert openai_settings.llm_model == "gpt-4o-mini"
    assert openai_settings.llm_api_key == "test-openai-key"

    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    openai_embedding_settings = get_settings()

    assert openai_embedding_settings.embedding_provider == "openai"
    assert openai_embedding_settings.openai_api_key == "test-openai-key"


def test_openai_embeddings_require_separate_openai_key(monkeypatch) -> None:
    monkeypatch.setenv("WRITER_API_KEY", "test-writer-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)

    settings = get_settings()

    assert settings.llm_api_key == "test-writer-key"
    assert settings.openai_api_key is None
    assert settings.embedding_provider == "hash"


def test_llm_api_key_is_writer_generation_fallback(monkeypatch) -> None:
    monkeypatch.delenv("WRITER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-llm-key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    settings = get_settings()

    assert settings.llm_provider == "writer"
    assert settings.llm_api_key == "test-llm-key"
    assert settings.llm_base_url == "https://api.writer.com/v1/chat/completions"


def test_openai_embedding_provider_requires_openai_key_not_writer_key(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WRITER_API_KEY", "test-writer-key")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = get_settings()
    provider = build_embedding_provider(
        provider=settings.embedding_provider,
        openai_api_key=settings.openai_api_key,
        embedding_model=settings.embedding_model,
    )

    assert settings.llm_api_key == "test-writer-key"
    assert settings.openai_api_key is None
    assert isinstance(provider, HashEmbeddingProvider)


def test_explicit_provider_env_overrides_auto_defaults(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("WRITER_API_KEY", "test-writer-key")
    monkeypatch.setenv("COHERE_API_KEY", "test-cohere-key")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("RERANKER_PROVIDER", "heuristic")

    settings = get_settings()

    assert settings.embedding_provider == "hash"
    assert settings.reranker_provider == "heuristic"
