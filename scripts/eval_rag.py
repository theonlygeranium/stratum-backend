#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.rag.hybrid import HybridRetriever  # noqa: E402


DEFAULT_GOLDEN = ROOT / "tests" / "fixtures" / "rag_golden.jsonl"
KB_DIR = ROOT / "data" / "knowledge_base"
MIN_SUBSTANTIVE_RESPONSE_CHARS = 80


def load_golden(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def evaluate_retrieval(cases: list[dict[str, Any]]) -> dict[str, Any]:
    start = time.perf_counter()
    settings = get_settings()
    retriever = HybridRetriever(
        settings.knowledge_base_dir,
        confidence_threshold=settings.confidence_threshold,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_api_key=settings.openai_api_key,
        vector_store_provider=settings.vector_store_provider,
        chroma_persist_dir=settings.chroma_persist_dir,
        pinecone_api_key=settings.pinecone_api_key,
        pinecone_index=settings.pinecone_index,
        pinecone_namespace=settings.pinecone_namespace,
        reranker_provider=settings.reranker_provider,
        reranker_model=settings.reranker_model,
        cohere_api_key=settings.cohere_api_key,
    )
    init_ms = (time.perf_counter() - start) * 1000

    hits = 0
    grounded_passes = 0
    latencies: list[float] = []
    details: list[dict[str, Any]] = []

    for case in cases:
        started = time.perf_counter()
        result = retriever.retrieve(case["query"], top_k=10)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        hit = _case_hit(case, result.docs)
        grounded = result.source.grounded is bool(case["should_ground"])
        if case["should_ground"]:
            grounded = grounded and hit
        hits += int(hit)
        grounded_passes += int(grounded)
        details.append(
            {
                "name": case["name"],
                "hit": hit,
                "grounded_pass": grounded,
                "source": result.source.model_dump(),
                "latency_ms": round(elapsed_ms, 2),
                "top_sources": [
                    {
                        "source_title": doc.metadata.get("source_title"),
                        "service_area": doc.metadata.get("service_area"),
                        "content_type": doc.metadata.get("content_type"),
                        "score": doc.metadata.get("relevance_score"),
                        "reranker_provider": doc.metadata.get("reranker_provider"),
                        "cross_encoder_score": doc.metadata.get("cross_encoder_score"),
                    }
                    for doc in result.docs[:3]
                ],
            }
        )

    return {
        "retriever_init_ms": round(init_ms, 2),
        "recall_at_10": round(hits / len(cases), 4),
        "groundedness_proxy": round(grounded_passes / len(cases), 4),
        "retrieval_latency_ms": {
            "p50": round(statistics.median(latencies), 2),
            "p95": round(_percentile(latencies, 95), 2),
        },
        "embedding_provider": retriever.embedding_provider,
        "vector_store_provider": retriever.vector_store_provider,
        "reranker_provider": retriever.reranker_provider,
        "reranker_model": retriever.reranker_model,
        "cases": details,
    }


def evaluate_first_token_latency() -> dict[str, Any]:
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("LLM_API_KEY", None)
    os.environ.pop("WRITER_API_KEY", None)
    os.environ.pop("COHERE_API_KEY", None)
    os.environ["EMBEDDING_PROVIDER"] = "hash"
    os.environ["VECTOR_STORE_PROVIDER"] = "chroma"
    os.environ["RERANKER_PROVIDER"] = "heuristic"
    os.environ["LLM_PROVIDER"] = "writer"

    from fastapi.testclient import TestClient

    import app.main as main_module

    client = TestClient(main_module.app)
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "What does EdStratum Labs do?",
                "timestamp": 0,
            }
        ],
        "mode": "open",
        "intakeIndex": None,
        "intakeAnswers": {},
        "sessionId": "eval-rag-first-token",
    }

    started = time.perf_counter()
    first_token_latency_ms: float | None = None
    tokens: list[str] = []
    with client.stream("POST", "/api/chat", json=payload) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line.removeprefix("data: "))
            if event.get("type") == "token":
                if first_token_latency_ms is None:
                    first_token_latency_ms = round(
                        (time.perf_counter() - started) * 1000,
                        2,
                    )
                tokens.append(str(event.get("token") or ""))

    response_text = " ".join("".join(tokens).split())
    substantive_response = (
        len(response_text) >= MIN_SUBSTANTIVE_RESPONSE_CHARS
        and response_text != "Here is the grounded read:"
    )
    return {
        "first_token_latency_ms": first_token_latency_ms,
        "substantive_response": substantive_response,
        "response_chars": len(response_text),
        "passed": (
            first_token_latency_ms is not None
            and first_token_latency_ms < 1500
            and substantive_response
        ),
    }


def _case_hit(case: dict[str, Any], docs: list[Any]) -> bool:
    if case["should_ground"] is False:
        return True
    for doc in docs:
        metadata = doc.metadata
        expected_title = case.get("expected_source_title")
        expected_area = case.get("expected_service_area")
        expected_type = case.get("expected_content_type")
        if expected_title and metadata.get("source_title") != expected_title:
            continue
        if expected_area and metadata.get("service_area") != expected_area:
            service_areas = metadata.get("service_areas") or []
            if expected_area not in service_areas:
                continue
        if expected_type and metadata.get("content_type") != expected_type:
            continue
        return True
    return False


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percentile / 100) * (len(ordered) - 1)))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate STRATUM RAG acceptance metrics.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    cases = load_golden(args.golden)
    retrieval = evaluate_retrieval(cases)
    first_token = evaluate_first_token_latency()
    passed = (
        retrieval["recall_at_10"] >= 0.90
        and retrieval["groundedness_proxy"] >= 0.85
        and first_token["passed"]
    )
    report = {
        "passed": passed,
        "thresholds": {
            "recall_at_10": 0.90,
            "groundedness_proxy": 0.85,
            "first_token_latency_ms": 1500,
        },
        "retrieval": retrieval,
        "sse": first_token,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"passed: {passed}")
        print(f"recall@10: {retrieval['recall_at_10']}")
        print(f"groundedness proxy: {retrieval['groundedness_proxy']}")
        print(f"first token latency ms: {first_token['first_token_latency_ms']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
