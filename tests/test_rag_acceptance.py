from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import scripts.eval_rag as eval_module
from scripts.eval_rag import DEFAULT_GOLDEN, evaluate_retrieval, load_golden


def test_rag_eval_meets_acceptance_thresholds() -> None:
    report = evaluate_retrieval(load_golden(DEFAULT_GOLDEN))

    assert report["recall_at_10"] >= 0.90
    assert report["groundedness_proxy"] >= 0.85
    assert report["retrieval_latency_ms"]["p95"] < 1500
    assert report["embedding_provider"] in {"hash", "openai"}
    assert report["vector_store_provider"] in {"chroma", "memory", "pinecone"}
    assert report["reranker_provider"] in {"heuristic", "cohere"}


def test_rag_eval_honors_configured_providers(monkeypatch) -> None:
    captured: dict[str, object] = {}

    settings = SimpleNamespace(
        knowledge_base_dir=Path("configured-kb"),
        confidence_threshold=0.61,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        openai_api_key="test-openai-key",
        vector_store_provider="pinecone",
        chroma_persist_dir=None,
        pinecone_api_key="test-pinecone-key",
        pinecone_index="stratum-test",
        pinecone_namespace="staging",
        reranker_provider="heuristic",
        reranker_model="rerank-v4.0-fast",
        cohere_api_key=None,
    )

    class FakeRetriever:
        embedding_provider = "openai"
        vector_store_provider = "pinecone"
        reranker_provider = "heuristic"
        reranker_model = "rerank-v4.0-fast"

        def __init__(self, knowledge_base_dir: Path, **kwargs: object):
            captured["knowledge_base_dir"] = knowledge_base_dir
            captured.update(kwargs)

        async def retrieve(self, query: str, top_k: int):
            del query, top_k
            return SimpleNamespace(
                source=SimpleNamespace(
                    grounded=True,
                    model_dump=lambda: {"grounded": True},
                ),
                docs=[
                    SimpleNamespace(
                        metadata={
                            "source_title": "Configured Source",
                            "service_area": "rag_engineering",
                            "content_type": "methodology",
                            "relevance_score": 0.99,
                        }
                    )
                ],
            )

    monkeypatch.setattr(eval_module, "get_settings", lambda: settings)
    monkeypatch.setattr(eval_module, "HybridRetriever", FakeRetriever)

    report = evaluate_retrieval(
        [
            {
                "name": "configured",
                "query": "How does RAG work?",
                "should_ground": True,
                "expected_source_title": "Configured Source",
                "expected_service_area": "rag_engineering",
                "expected_content_type": "methodology",
            }
        ]
    )

    assert report["embedding_provider"] == "openai"
    assert report["vector_store_provider"] == "pinecone"
    assert captured == {
        "knowledge_base_dir": Path("configured-kb"),
        "confidence_threshold": 0.61,
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "embedding_api_key": "test-openai-key",
        "vector_store_provider": "pinecone",
        "chroma_persist_dir": None,
        "pinecone_api_key": "test-pinecone-key",
        "pinecone_index": "stratum-test",
        "pinecone_namespace": "staging",
        "reranker_provider": "heuristic",
        "reranker_model": "rerank-v4.0-fast",
        "cohere_api_key": None,
    }
