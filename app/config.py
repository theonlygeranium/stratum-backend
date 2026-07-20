from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    allowed_origins: list[str]
    confidence_threshold: float
    calendly_url: str
    knowledge_base_dir: Path
    escalation_log_dir: Path
    database_url: str | None
    embedding_provider: str
    embedding_model: str
    vector_store_provider: str
    chroma_persist_dir: Path | None
    reranker_provider: str
    reranker_model: str
    cohere_api_key: str | None
    llm_api_key: str | None
    llm_base_url: str
    llm_model: str
    resend_api_key: str | None
    jeffrey_email: str | None


def get_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    origins = os.getenv(
        "ALLOWED_ORIGINS",
        "https://edstratumlabs.ai,https://www.edstratumlabs.ai,"
        "https://edstratumlabs.pages.dev,http://localhost:5173",
    )
    kb_dir = Path(os.getenv("KNOWLEDGE_BASE_DIR", "data/knowledge_base"))
    log_dir = Path(os.getenv("ESCALATION_LOG_DIR", "data/escalations"))
    chroma_dir_value = os.getenv("CHROMA_PERSIST_DIR")
    chroma_dir = Path(chroma_dir_value) if chroma_dir_value else None
    if not kb_dir.is_absolute():
        kb_dir = root / kb_dir
    if not log_dir.is_absolute():
        log_dir = root / log_dir
    if chroma_dir and not chroma_dir.is_absolute():
        chroma_dir = root / chroma_dir

    openai_api_key = os.getenv("OPENAI_API_KEY") or None
    cohere_api_key = os.getenv("COHERE_API_KEY") or None

    return Settings(
        allowed_origins=_split_csv(origins),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.55")),
        calendly_url=os.getenv(
            "CALENDLY_URL", "https://calendly.com/edstratumlabs/discovery"
        ),
        knowledge_base_dir=kb_dir,
        escalation_log_dir=log_dir,
        database_url=os.getenv("DATABASE_URL") or None,
        embedding_provider=(
            os.getenv("EMBEDDING_PROVIDER")
            or ("openai" if openai_api_key else "hash")
        ),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        vector_store_provider=os.getenv("VECTOR_STORE_PROVIDER", "chroma"),
        chroma_persist_dir=chroma_dir,
        reranker_provider=(
            os.getenv("RERANKER_PROVIDER")
            or ("cohere" if cohere_api_key else "heuristic")
        ),
        reranker_model=os.getenv("RERANKER_MODEL", "rerank-v4.0-fast"),
        cohere_api_key=cohere_api_key,
        # LLM provider — configurable via env vars.
        # Defaults to OpenAI (api.openai.com / gpt-4o).
        # Set LLM_API_KEY + LLM_BASE_URL + LLM_MODEL to swap to
        # WRITER Palmyra or any OpenAI-compatible endpoint.
        # Backward compat: OPENAI_API_KEY is still read if LLM_API_KEY
        # is absent.
        llm_api_key=(
            os.getenv("LLM_API_KEY")
            or openai_api_key
            or None
        ),
        llm_base_url=os.getenv(
            "LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"
        ),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
        resend_api_key=os.getenv("RESEND_API_KEY") or None,
        jeffrey_email=os.getenv("JEFFREY_EMAIL") or None,
    )
