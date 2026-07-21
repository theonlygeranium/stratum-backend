from __future__ import annotations

import asyncio

from app.rag.rerankers import CohereReranker, HeuristicReranker, RerankCandidate


def _candidate(index: int, heuristic_score: float) -> RerankCandidate:
    return RerankCandidate(
        index=index,
        text=f"Candidate {index}",
        fused_score=0.01,
        bm25_score=0.5,
        semantic_score=0.5,
        heuristic_score=heuristic_score,
    )


def test_heuristic_reranker_orders_by_local_score() -> None:
    results = asyncio.run(
        HeuristicReranker().rerank(
            "query",
            [_candidate(1, 0.4), _candidate(2, 0.8), _candidate(3, 0.6)],
        )
    )

    assert [result.index for result in results] == [2, 3, 1]
    assert {result.provider for result in results} == {"heuristic"}


def test_cohere_reranker_uses_cross_encoder_scores(monkeypatch) -> None:
    captured_payload = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.92},
                    {"index": 0, "relevance_score": 0.12},
                ]
            }

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, endpoint: str, *, headers: dict, json: dict) -> FakeResponse:
            captured_payload["endpoint"] = endpoint
            captured_payload["headers"] = headers
            captured_payload["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.rag.rerankers.httpx.AsyncClient", FakeClient)

    results = asyncio.run(
        CohereReranker(api_key="test-key", model="rerank-v4.0-fast").rerank(
            "query",
            [_candidate(10, 0.8), _candidate(20, 0.2)],
        )
    )

    assert [result.index for result in results] == [20, 10]
    assert results[0].provider == "cohere"
    assert results[0].model == "rerank-v4.0-fast"
    assert results[0].cross_encoder_score == 0.92
    assert captured_payload["endpoint"].endswith("/v2/rerank")
    assert captured_payload["json"]["documents"] == ["Candidate 10", "Candidate 20"]
    assert captured_payload["json"]["top_n"] == 2
