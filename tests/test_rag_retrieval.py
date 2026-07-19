from __future__ import annotations

from pathlib import Path

from app.rag.chunker import chunk_documents
from app.rag.documents import Document, load_knowledge_base
from app.rag.hybrid import HybridRetriever


BACKEND_DIR = Path(__file__).resolve().parents[1]
KB_DIR = BACKEND_DIR / "data" / "knowledge_base"
REQUIRED_METADATA = {
    "service_area",
    "content_type",
    "freshness_date",
    "source_title",
    "source_url",
}


def test_kb_documents_have_phase_2_metadata() -> None:
    docs = load_knowledge_base(KB_DIR)

    assert docs
    assert {doc.metadata["content_type"] for doc in docs} >= {
        "case_study",
        "intake_logic",
        "methodology",
        "service",
        "site_copy",
        "technical_doc",
    }
    for doc in docs:
        assert REQUIRED_METADATA <= set(doc.metadata)
        assert all(doc.metadata[key] for key in REQUIRED_METADATA - {"source_url"})


def test_chunker_preserves_section_metadata() -> None:
    doc = Document(
        content=(
            "# Source\n\n"
            "Opening context.\n\n"
            "## Canvas Workflow\n\n"
            "Canvas LTI placement and gradebook context.\n\n"
            "## RAG Workflow\n\n"
            "Grounded retrieval and source confidence context."
        ),
        metadata={"source_title": "Synthetic Source", "source_id": "synthetic"},
    )

    chunks = chunk_documents([doc], chunk_size=120)

    assert len(chunks) >= 3
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.metadata["chunk_id"].startswith("synthetic:") for chunk in chunks)
    assert {chunk.metadata["section_title"] for chunk in chunks} >= {
        "Source",
        "Source > Canvas Workflow",
        "Source > RAG Workflow",
    }


def test_canvas_lti_query_retrieves_canvas_source() -> None:
    result = HybridRetriever(KB_DIR).retrieve(
        "Can you help with Canvas LTI grade passback, Developer Keys, and roster sync?",
        top_k=5,
    )

    assert result.source.grounded is True
    assert result.source.score >= 0.55
    assert result.docs[0].metadata["service_area"] == "canvas"
    assert "Canvas" in result.source.label


def test_ai_roadmap_query_retrieves_strategy_source() -> None:
    result = HybridRetriever(KB_DIR).retrieve(
        "How should we build an AI roadmap with ROI, governance, and vendor review?",
        top_k=5,
    )

    assert result.source.grounded is True
    assert result.docs[0].metadata["service_area"] == "ai_strategy"
    assert result.docs[0].metadata["content_type"] in {"methodology", "service"}


def test_rag_quality_query_retrieves_rag_source() -> None:
    result = HybridRetriever(KB_DIR).retrieve(
        "What makes a RAG system grounded with semantic chunking, BM25, reranking, and confidence?",
        top_k=5,
    )

    assert result.source.grounded is True
    assert result.docs[0].metadata["service_area"] == "rag_engineering"
    assert result.docs[0].metadata["content_type"] == "methodology"


def test_intake_query_retrieves_intake_logic() -> None:
    result = HybridRetriever(KB_DIR).retrieve(
        "How does STRATUM intake scoring decide high intent and readiness snapshots?",
        top_k=5,
    )

    assert result.source.grounded is True
    assert result.docs[0].metadata["content_type"] == "intake_logic"


def test_ai_adjacent_off_topic_query_stays_low_confidence() -> None:
    result = HybridRetriever(KB_DIR).retrieve(
        "Can AI recommend a backpacking route in Iceland?",
        top_k=5,
    )

    assert result.source.grounded is False
    assert result.source.score < 0.55
