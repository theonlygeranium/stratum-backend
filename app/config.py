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
    openai_api_key: str | None
    writer_api_key: str | None
    cohere_api_key: str | None
    llm_api_key: str | None
    llm_provider: str
    llm_base_url: str
    llm_model: str
    resend_api_key: str | None
    jeffrey_email: str | None
    resend_from_email: str
    elevenlabs_api_key: str | None
    elevenlabs_voice_id: str


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
    writer_api_key = os.getenv("WRITER_API_KEY") or None
    cohere_api_key = os.getenv("COHERE_API_KEY") or None
    llm_provider_env = os.getenv("LLM_PROVIDER")
    llm_base_url_env = os.getenv("LLM_BASE_URL")
    llm_provider = (
        llm_provider_env
        or (
            "openai"
            if llm_base_url_env and "api.openai.com" in llm_base_url_env
            else "writer"
        )
    ).strip().lower()
    if llm_base_url_env:
        llm_base_url = llm_base_url_env
    elif llm_provider == "openai":
        llm_base_url = "https://api.openai.com/v1/chat/completions"
    else:
        llm_base_url = "https://api.writer.com/v1/chat/completions"
    llm_api_key_override = os.getenv("LLM_API_KEY") or None
    if llm_provider == "openai" or "api.openai.com" in llm_base_url:
        llm_api_key = llm_api_key_override or openai_api_key
    else:
        llm_api_key = writer_api_key or llm_api_key_override

    return Settings(
        allowed_origins=_split_csv(origins),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.55")),
        calendly_url=os.getenv("CALENDLY_URL") or "",
        knowledge_base_dir=kb_dir,
        escalation_log_dir=log_dir,
        database_url=os.getenv("DATABASE_URL") or None,
        embedding_provider=(os.getenv("EMBEDDING_PROVIDER") or "hash").strip().lower(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        vector_store_provider=os.getenv("VECTOR_STORE_PROVIDER", "chroma"),
        chroma_persist_dir=chroma_dir,
        reranker_provider=(
            os.getenv("RERANKER_PROVIDER")
            or ("cohere" if cohere_api_key else "heuristic")
        ),
        reranker_model=os.getenv("RERANKER_MODEL", "rerank-v4.0-fast"),
        openai_api_key=openai_api_key,
        writer_api_key=writer_api_key,
        cohere_api_key=cohere_api_key,
        # Generative LLM defaults to WRITER Palmyra. OPENAI_API_KEY is kept
        # separate for embeddings unless OpenAI is explicitly selected.
        llm_api_key=llm_api_key,
        llm_provider=llm_provider,
        llm_base_url=llm_base_url,
        llm_model=os.getenv(
            "LLM_MODEL",
            "gpt-4o-mini" if llm_provider == "openai" else "palmyra-x5",
        ),
        resend_api_key=os.getenv("RESEND_API_KEY") or None,
        jeffrey_email=(
            os.getenv("ESCALATION_EMAIL_TO")
            or os.getenv("JEFFREY_EMAIL")
            or None
        ),
        resend_from_email=(
            os.getenv("ESCALATION_EMAIL_FROM")
            or os.getenv("RESEND_FROM_EMAIL")
            or "stratum@edstratumlabs.ai"
        ),
        elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY") or None,
        elevenlabs_voice_id=(
            os.getenv("ELEVENLABS_VOICE_ID")
            or "JBFqnCBsd6RMkjVDRZzb"
        ),
    )
