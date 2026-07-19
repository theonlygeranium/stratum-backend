from __future__ import annotations

import re
from dataclasses import dataclass

from app.rag.documents import Document


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class _Section:
    title: str
    content: str


def chunk_documents(
    docs: list[Document],
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 180,
) -> list[Document]:
    chunks: list[Document] = []
    for doc in docs:
        sections = _split_semantic_sections(doc.content)
        chunk_index = 0
        for section in sections:
            for piece in _split_section(section, chunk_size, chunk_overlap):
                chunks.append(_make_chunk(doc, piece, chunk_index, section.title))
                chunk_index += 1
    return chunks


def _split_semantic_sections(text: str) -> list[_Section]:
    sections: list[_Section] = []
    current: list[str] = []
    heading_path: list[str] = []
    current_title = "Overview"

    for line in text.splitlines():
        stripped = line.strip()
        heading = HEADING_RE.match(stripped)
        if heading and current:
            sections.append(_Section(title=current_title, content="\n".join(current).strip()))
            current = []
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_path = heading_path[: level - 1]
            heading_path.append(title)
            current_title = " > ".join(heading_path)
        current.append(line.rstrip())

    if current:
        sections.append(_Section(title=current_title, content="\n".join(current).strip()))
    return sections


def _split_section(section: _Section, chunk_size: int, chunk_overlap: int) -> list[str]:
    content = section.content.strip()
    if not content:
        return []
    if len(content) <= chunk_size:
        return [content]

    pieces: list[str] = []
    current: list[str] = []

    for block in _paragraph_blocks(content):
        if len(block) > chunk_size:
            if current:
                pieces.append(_join_blocks(current))
                current = []
            pieces.extend(_split_oversized_block(block, chunk_size, chunk_overlap))
            continue

        candidate = _join_blocks([*current, block])
        if not current or len(candidate) <= chunk_size:
            current.append(block)
            continue

        previous = _join_blocks(current)
        pieces.append(previous)
        overlap = _semantic_overlap(previous, chunk_overlap)
        current = [overlap, block] if overlap else [block]

    if current:
        pieces.append(_join_blocks(current))

    return [_ensure_section_context(piece, section.title) for piece in pieces if piece.strip()]


def _paragraph_blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def _join_blocks(blocks: list[str]) -> str:
    return "\n\n".join(block.strip() for block in blocks if block.strip()).strip()


def _split_oversized_block(block: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(block) if sentence.strip()]
    if len(sentences) <= 1:
        return _split_words(block, chunk_size, chunk_overlap)

    pieces: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*current, sentence]).strip()
        if current and len(candidate) > chunk_size:
            previous = " ".join(current).strip()
            pieces.append(previous)
            overlap = _semantic_overlap(previous, chunk_overlap)
            current = [overlap, sentence] if overlap else [sentence]
        else:
            current.append(sentence)
    if current:
        pieces.append(" ".join(current).strip())
    return pieces


def _split_words(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word]).strip()
        if current and len(candidate) > chunk_size:
            previous = " ".join(current).strip()
            pieces.append(previous)
            overlap_words = _semantic_overlap(previous, chunk_overlap).split()
            current = [*overlap_words, word]
        else:
            current.append(word)
    if current:
        pieces.append(" ".join(current).strip())
    return pieces


def _semantic_overlap(text: str, limit: int) -> str:
    blocks = _paragraph_blocks(text)
    overlap: list[str] = []
    for block in reversed(blocks):
        candidate = _join_blocks([block, *overlap])
        if len(candidate) > limit and overlap:
            break
        if len(candidate) > limit:
            sentences = SENTENCE_RE.split(block)
            return " ".join(sentences[-2:]).strip()[-limit:]
        overlap.insert(0, block)
    return _join_blocks(overlap)


def _ensure_section_context(piece: str, section_title: str) -> str:
    if not section_title or piece.lstrip().startswith("#"):
        return piece.strip()
    return f"## {section_title}\n\n{piece.strip()}"


def _make_chunk(doc: Document, content: str, index: int, section_title: str) -> Document:
    metadata = dict(doc.metadata)
    metadata["chunk_index"] = index
    metadata["section_title"] = section_title
    metadata["chunk_id"] = f"{metadata.get('source_id', 'source')}:{index}"
    metadata["content_length"] = len(content)
    return Document(content=content, metadata=metadata)
