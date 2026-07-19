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
    openai_api_key: str | None
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
    if not kb_dir.is_absolute():
        kb_dir = root / kb_dir
    if not log_dir.is_absolute():
        log_dir = root / log_dir

    return Settings(
        allowed_origins=_split_csv(origins),
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.40")),
        calendly_url=os.getenv(
            "CALENDLY_URL", "https://calendly.com/edstratumlabs/discovery"
        ),
        knowledge_base_dir=kb_dir,
        escalation_log_dir=log_dir,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
        resend_api_key=os.getenv("RESEND_API_KEY") or None,
        jeffrey_email=os.getenv("JEFFREY_EMAIL") or None,
    )

