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

from app.rag.hybrid import HybridRetriever  # noqa: E402


DEFAULT_GOLDEN = ROOT / "tests" / "fixtures" / "rag_golden.jsonl"
KB_DIR = ROOT / "data" / "knowledge_base"


def load_golden(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def evaluate_retrieval(cases: list[dict[str, Any]]) -> dict[str, Any]:
    start = time.perf_counter()
    retriever = HybridRetriever(KB_DIR)
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
        "cases": details,
    }


def evaluate_first_token_latency() -> dict[str, Any]:
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ.pop("LLM_API_KEY", None)
    os.environ["EMBEDDING_PROVIDER"] = "hash"

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
    with client.stream("POST", "/api/chat", json=payload) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line.removeprefix("data: "))
            if event.get("type") == "token":
                return {
                    "first_token_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "passed": (time.perf_counter() - started) < 1.5,
                }
    return {"first_token_latency_ms": None, "passed": False}


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
