from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


LIST_METADATA_KEYS = {"aliases", "service_areas", "topics"}

DEFAULT_METADATA: dict[str, object] = {
    "source_url": "",
    "service_area": "general",
    "content_type": "site_copy",
    "freshness_date": "",
}


@dataclass(frozen=True)
class Document:
    content: str
    metadata: dict[str, object] = field(default_factory=dict)


def _parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, text

    metadata: dict[str, object] = {}
    for line in lines[1:end_index]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        metadata[key] = _parse_metadata_value(key, value)

    body = "\n".join(lines[end_index + 1 :]).strip()
    return metadata, body


def _parse_metadata_value(key: str, value: str) -> object:
    cleaned = value.strip().strip('"').strip("'")
    if key not in LIST_METADATA_KEYS:
        return cleaned

    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    return [
        item.strip().strip('"').strip("'")
        for item in cleaned.split(",")
        if item.strip()
    ]


def _normalize_metadata(path: Path, metadata: dict[str, object]) -> dict[str, object]:
    normalized = dict(DEFAULT_METADATA)
    normalized.update(metadata)
    if not normalized.get("freshness_date"):
        try:
            mtime = os.path.getmtime(path)
            normalized["freshness_date"] = datetime.fromtimestamp(mtime).strftime(
                "%Y-%m-%d"
            )
        except OSError:
            normalized["freshness_date"] = ""
    normalized.setdefault("source_title", path.stem.replace("-", " ").title())

    for key in ("source_title", "source_url", "service_area", "content_type", "freshness_date"):
        value = normalized.get(key)
        normalized[key] = str(value).strip() if value is not None else ""

    if not normalized["source_title"]:
        normalized["source_title"] = path.stem.replace("-", " ").title()
    if not normalized["service_area"]:
        normalized["service_area"] = "general"
    if not normalized["content_type"]:
        normalized["content_type"] = "site_copy"
    for key in LIST_METADATA_KEYS:
        value = normalized.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            normalized[key] = [str(item).strip() for item in value if str(item).strip()]
        else:
            normalized[key] = [
                item.strip()
                for item in str(value).split(",")
                if item.strip()
            ]

    normalized["file_path"] = str(path)
    normalized["source_id"] = path.stem
    return normalized


def load_knowledge_base(directory: Path) -> list[Document]:
    docs: list[Document] = []
    if not directory.exists():
        return docs
    for path in sorted(directory.rglob("*.md")):
        metadata, body = _parse_front_matter(path.read_text(encoding="utf-8"))
        docs.append(Document(content=body, metadata=_normalize_metadata(path, metadata)))
    return docs
