from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Protocol

from app.observability import increment_counter, log_event


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.+#-]*")


class EmbeddingProvider(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class HashEmbeddingProvider:
    name = "hash"

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        buckets = [0.0] * self.dimensions
        counts = Counter(TOKEN_RE.findall(text.lower()))
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            buckets[bucket] += sign * (1.0 + math.log(count))
        return _normalize(buckets)


class OpenAIEmbeddingProvider:
    name = "openai"

    def __init__(self, *, api_key: str, model: str):
        from langchain_openai import OpenAIEmbeddings

        self._client = OpenAIEmbeddings(api_key=api_key, model=model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


class DenseVectorIndex:
    def __init__(
        self,
        texts: list[str],
        *,
        metadatas: list[dict[str, object]] | None = None,
        embedding_provider: EmbeddingProvider,
        vector_store_provider: str,
        chroma_persist_dir: Path | None = None,
        pinecone_api_key: str | None = None,
        pinecone_index: str | None = None,
        pinecone_namespace: str | None = None,
    ):
        self.texts = texts
        self.metadatas = _normalize_metadatas(metadatas, len(texts))
        self.embedding_provider = embedding_provider
        self.vector_store_provider = "memory"
        self._collection = None
        self._pinecone_index = None
        self._pinecone_namespace = pinecone_namespace or ""

        try:
            self._embeddings = embedding_provider.embed_documents(texts)
        except Exception as exc:
            log_event(
                "warning",
                "vector_store_degraded",
                from_provider=embedding_provider.name,
                to_provider="hash",
                error_type=type(exc).__name__,
            )
            increment_counter("vector_store_degradation")
            self.embedding_provider = HashEmbeddingProvider()
            self._embeddings = self.embedding_provider.embed_documents(texts)

        requested_store = (vector_store_provider or "chroma").strip().lower()
        if requested_store == "pinecone":
            self._build_pinecone(
                api_key=pinecone_api_key,
                index_name=pinecone_index,
            )
            if self.vector_store_provider != "pinecone":
                self._build_chroma(chroma_persist_dir)
        elif requested_store == "chroma":
            self._build_chroma(chroma_persist_dir)

    def rank(self, query: str, indexes: list[int]) -> list[tuple[int, float]]:
        if not self.texts:
            return []
        query_embedding = self.embedding_provider.embed_query(query)
        allowed = set(indexes)
        if self._pinecone_index is not None:
            return self._rank_pinecone(query_embedding, allowed, indexes)
        if self._collection is not None:
            try:
                return self._rank_chroma(query_embedding, allowed)
            except Exception as exc:
                log_event(
                    "warning",
                    "vector_store_degraded",
                    from_provider="chroma",
                    to_provider="memory",
                    error_type=type(exc).__name__,
                )
                increment_counter("vector_store_degradation")
                self._collection = None
                self.vector_store_provider = "memory"
                return self._rank_memory(query_embedding, indexes)
        return self._rank_memory(query_embedding, indexes)

    def _build_pinecone(
        self,
        *,
        api_key: str | None,
        index_name: str | None,
    ) -> None:
        if not api_key or not index_name:
            log_event(
                "warning",
                "vector_store_degraded",
                from_provider="pinecone",
                to_provider="chroma",
                error_type="configuration_missing",
            )
            increment_counter("vector_store_degradation")
            self._pinecone_index = None
            return

        try:
            from pinecone import Pinecone

            client = Pinecone(api_key=api_key)
            index = client.Index(index_name)
            vectors = [
                {
                    "id": f"stratum-kb-{position}",
                    "values": embedding,
                    "metadata": self.metadatas[position],
                }
                for position, embedding in enumerate(self._embeddings)
            ]
            if vectors:
                index.upsert(
                    vectors=vectors,
                    namespace=self._pinecone_namespace,
                )
            self._pinecone_index = index
            self.vector_store_provider = "pinecone"
        except Exception as exc:
            log_event(
                "warning",
                "vector_store_degraded",
                from_provider="pinecone",
                to_provider="chroma",
                error_type=type(exc).__name__,
            )
            increment_counter("vector_store_degradation")
            self._pinecone_index = None

    def _build_chroma(self, persist_dir: Path | None) -> None:
        try:
            import chromadb
            from chromadb.config import Settings

            if persist_dir:
                client = chromadb.PersistentClient(
                    path=str(persist_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
            else:
                client = chromadb.Client(Settings(anonymized_telemetry=False))
            collection = client.get_or_create_collection(
                name="stratum_kb",
                metadata={"hnsw:space": "cosine"},
            )
            ids = [str(index) for index in range(len(self.texts))]
            existing = set(collection.get(ids=ids).get("ids", []))
            missing = [index for index in range(len(self.texts)) if str(index) not in existing]
            if missing:
                collection.add(
                    ids=[str(index) for index in missing],
                    documents=[self.texts[index] for index in missing],
                    embeddings=[self._embeddings[index] for index in missing],
                    metadatas=[self.metadatas[index] for index in missing],
                )
            self._collection = collection
            self.vector_store_provider = "chroma"
        except Exception as exc:
            log_event(
                "warning",
                "vector_store_degraded",
                from_provider="chroma",
                to_provider="memory",
                error_type=type(exc).__name__,
            )
            increment_counter("vector_store_degradation")
            self._collection = None
            self.vector_store_provider = "memory"

    def _rank_chroma(
        self,
        query_embedding: list[float],
        allowed: set[int],
    ) -> list[tuple[int, float]]:
        if self._collection is None:
            return []
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=len(self.texts),
            include=["distances", "metadatas"],
        )
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        ranked: list[tuple[int, float]] = []
        for metadata, distance in zip(metadatas, distances, strict=False):
            index = int(metadata.get("index", -1))
            if index not in allowed:
                continue
            ranked.append((index, 1.0 / (1.0 + float(distance))))
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def _rank_pinecone(
        self,
        query_embedding: list[float],
        allowed: set[int],
        indexes: list[int],
    ) -> list[tuple[int, float]]:
        if self._pinecone_index is None:
            return []

        try:
            result = self._pinecone_index.query(
                vector=query_embedding,
                top_k=len(self.texts),
                include_metadata=True,
                namespace=self._pinecone_namespace,
            )
        except Exception as exc:
            log_event(
                "warning",
                "vector_store_degraded",
                from_provider="pinecone",
                to_provider="memory",
                error_type=type(exc).__name__,
            )
            increment_counter("vector_store_degradation")
            return self._rank_memory(query_embedding, indexes)

        ranked: list[tuple[int, float]] = []
        for match in _pinecone_matches(result):
            metadata = _pinecone_match_metadata(match)
            index = int(metadata.get("index", -1))
            if index not in allowed:
                continue
            ranked.append((index, _pinecone_match_score(match)))
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def _rank_memory(
        self,
        query_embedding: list[float],
        indexes: list[int],
    ) -> list[tuple[int, float]]:
        scores = [
            (index, _cosine(query_embedding, self._embeddings[index]))
            for index in indexes
        ]
        return sorted(scores, key=lambda item: item[1], reverse=True)


def build_embedding_provider(
    *,
    provider: str,
    openai_api_key: str | None,
    embedding_model: str,
) -> EmbeddingProvider:
    if provider == "openai" and openai_api_key:
        try:
            return OpenAIEmbeddingProvider(
                api_key=openai_api_key,
                model=embedding_model,
            )
        except Exception as exc:
            log_event(
                "warning",
                "vector_store_degraded",
                from_provider="openai",
                to_provider="hash",
                error_type=type(exc).__name__,
            )
            increment_counter("vector_store_degradation")
            pass
    return HashEmbeddingProvider()


def _pinecone_matches(result: object) -> list[object]:
    if isinstance(result, dict):
        matches = result.get("matches", [])
    else:
        matches = getattr(result, "matches", [])
    return list(matches or [])


def _pinecone_match_metadata(match: object) -> dict[str, object]:
    if isinstance(match, dict):
        metadata = match.get("metadata", {})
    else:
        metadata = getattr(match, "metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _pinecone_match_score(match: object) -> float:
    if isinstance(match, dict):
        score = match.get("score", 0.0)
    else:
        score = getattr(match, "score", 0.0)
    return float(score or 0.0)


def _normalize_metadatas(
    metadatas: list[dict[str, object]] | None,
    length: int,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    supplied = metadatas or []
    for index in range(length):
        metadata = dict(supplied[index]) if index < len(supplied) else {}
        metadata["index"] = index
        normalized.append(_sanitize_metadata(metadata))
    return normalized


def _sanitize_metadata(metadata: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in metadata.items():
        if isinstance(value, str | int | float | bool):
            sanitized[key] = value
        elif value is not None:
            sanitized[key] = str(value)
    return sanitized


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
