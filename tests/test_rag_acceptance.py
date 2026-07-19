from __future__ import annotations

from scripts.eval_rag import DEFAULT_GOLDEN, evaluate_retrieval, load_golden


def test_rag_eval_meets_acceptance_thresholds() -> None:
    report = evaluate_retrieval(load_golden(DEFAULT_GOLDEN))

    assert report["recall_at_10"] >= 0.90
    assert report["groundedness_proxy"] >= 0.85
    assert report["retrieval_latency_ms"]["p95"] < 1500
    assert report["embedding_provider"] in {"hash", "openai"}
    assert report["vector_store_provider"] in {"chroma", "memory"}
