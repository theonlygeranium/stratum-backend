from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.observability import increment_counter, log_event


@dataclass(frozen=True)
class RerankCandidate:
    index: int
    text: str
    fused_score: float
    bm25_score: float
    semantic_score: float
    heuristic_score: float


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float
    provider: str
    model: str | None = None
    cross_encoder_score: float | None = None


class Reranker(Protocol):
    name: str
    model: str | None

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> list[RerankResult]:
        ...


class HeuristicReranker:
    name = "heuristic"
    model = None

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> list[RerankResult]:
        del query
        return [
            RerankResult(
                index=candidate.index,
                score=candidate.heuristic_score,
                provider=self.name,
            )
            for candidate in sorted(
                candidates,
                key=lambda item: (
                    -item.heuristic_score,
                    -item.fused_score,
                    item.index,
                ),
            )
        ]


class CohereReranker:
    name = "cohere"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "rerank-v4.0-fast",
        endpoint: str = "https://api.cohere.com/v2/rerank",
        timeout: float = 8.0,
    ):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self._fallback = HeuristicReranker()

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RerankCandidate],
    ) -> list[RerankResult]:
        if not candidates:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": [candidate.text for candidate in candidates],
                        "top_n": len(candidates),
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            log_event(
                "warning",
                "cohere_rerank_fallback",
                error_type=type(exc).__name__,
                model=self.model,
            )
            increment_counter("cohere_rerank_failure")
            return await self._fallback.rerank(query, candidates)

        by_position = list(candidates)
        by_index = {candidate.index: candidate for candidate in candidates}
        ranked: list[RerankResult] = []
        seen: set[int] = set()
        for item in data.get("results", []):
            position = int(item.get("index", -1))
            if position < 0 or position >= len(by_position):
                continue
            candidate = by_position[position]
            seen.add(candidate.index)
            cross_score = _normalize_cross_encoder_score(
                float(item.get("relevance_score", 0.0))
            )
            ranked.append(
                RerankResult(
                    index=candidate.index,
                    score=_blend_cross_encoder_score(cross_score, candidate),
                    provider=self.name,
                    model=self.model,
                    cross_encoder_score=cross_score,
                )
            )

        for result in await self._fallback.rerank(query, candidates):
            if result.index in seen:
                continue
            candidate = by_index[result.index]
            ranked.append(
                RerankResult(
                    index=result.index,
                    score=result.score,
                    provider=f"{self.name}_partial_fallback",
                    model=self.model,
                    cross_encoder_score=None,
                )
            )
            seen.add(candidate.index)

        return sorted(ranked, key=lambda item: (-item.score, item.index))


def build_reranker(
    *,
    provider: str,
    cohere_api_key: str | None,
    model: str,
) -> Reranker:
    normalized = provider.strip().lower()
    if normalized in {"auto", "cohere"} and cohere_api_key:
        return CohereReranker(api_key=cohere_api_key, model=model)
    return HeuristicReranker()


def _normalize_cross_encoder_score(score: float) -> float:
    if 0.0 <= score <= 1.0:
        return score
    return max(0.0, min(1.0, (score + 1.0) / 2.0))


def _blend_cross_encoder_score(
    cross_encoder_score: float,
    candidate: RerankCandidate,
) -> float:
    score = (
        cross_encoder_score * 0.72
        + candidate.heuristic_score * 0.20
        + candidate.semantic_score * 0.05
        + min(1.0, candidate.fused_score * 60) * 0.03
    )
    return max(0.0, min(1.0, score))
