from __future__ import annotations

import sys
from types import SimpleNamespace

from app.rag.vector_store import (
    DenseVectorIndex,
    HashEmbeddingProvider,
    build_embedding_provider,
)


class StaticEmbeddingProvider:
    name = "static"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        normalized = text.lower()
        if "beta" in normalized:
            return [0.0, 1.0]
        if "alpha" in normalized:
            return [1.0, 0.0]
        return [0.5, 0.5]


def test_pinecone_vector_store_upserts_and_ranks(monkeypatch) -> None:
    created: dict[str, object] = {}

    class FakeIndex:
        def __init__(self):
            self.records: list[dict] = []
            self.upsert_namespace: str | None = None

        def upsert(self, *, vectors: list[dict], namespace: str) -> None:
            self.records = vectors
            self.upsert_namespace = namespace

        def query(
            self,
            *,
            vector: list[float],
            top_k: int,
            include_metadata: bool,
            namespace: str,
        ) -> dict:
            assert include_metadata is True
            assert namespace == "staging"
            matches = [
                {
                    "metadata": record["metadata"],
                    "score": sum(
                        left * right
                        for left, right in zip(vector, record["values"], strict=False)
                    ),
                }
                for record in self.records
            ]
            return {
                "matches": sorted(
                    matches,
                    key=lambda match: match["score"],
                    reverse=True,
                )[:top_k]
            }

    class FakePinecone:
        def __init__(self, *, api_key: str):
            created["api_key"] = api_key

        def Index(self, name: str) -> FakeIndex:  # noqa: N802 - mirrors SDK API
            created["index_name"] = name
            index = FakeIndex()
            created["index"] = index
            return index

    monkeypatch.setitem(
        sys.modules,
        "pinecone",
        SimpleNamespace(Pinecone=FakePinecone),
    )

    index = DenseVectorIndex(
        ["alpha service", "beta service"],
        embedding_provider=StaticEmbeddingProvider(),
        vector_store_provider="pinecone",
        pinecone_api_key="test-pinecone-key",
        pinecone_index="stratum-test",
        pinecone_namespace="staging",
    )

    fake_index = created["index"]
    assert index.vector_store_provider == "pinecone"
    assert created["api_key"] == "test-pinecone-key"
    assert created["index_name"] == "stratum-test"
    assert fake_index.upsert_namespace == "staging"
    assert [record["id"] for record in fake_index.records] == [
        "stratum-kb-0",
        "stratum-kb-1",
    ]
    assert [record["metadata"]["index"] for record in fake_index.records] == [0, 1]

    assert index.rank("beta", [0, 1])[0][0] == 1
    assert [result[0] for result in index.rank("beta", [0])] == [0]


def test_pinecone_missing_config_falls_back_to_chroma_or_memory() -> None:
    index = DenseVectorIndex(
        ["alpha service"],
        embedding_provider=StaticEmbeddingProvider(),
        vector_store_provider="pinecone",
        pinecone_api_key=None,
        pinecone_index="stratum-test",
    )

    assert index.vector_store_provider in {"chroma", "memory"}
    assert index.rank("alpha", [0])


def test_openai_embedding_provider_can_be_constructed_with_fake_sdk(
    monkeypatch,
) -> None:
    class FakeOpenAIEmbeddings:
        def __init__(self, *, api_key: str, model: str):
            self.api_key = api_key
            self.model = model

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[float(len(text))] for text in texts]

        def embed_query(self, text: str) -> list[float]:
            return [float(len(text))]

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(OpenAIEmbeddings=FakeOpenAIEmbeddings),
    )

    provider = build_embedding_provider(
        provider="openai",
        openai_api_key="test-openai-key",
        embedding_model="text-embedding-3-small",
    )

    assert provider.name == "openai"
    assert provider.embed_documents(["abc"]) == [[3.0]]
    assert provider.embed_query("abcd") == [4.0]


def test_openai_embedding_provider_falls_back_without_key() -> None:
    provider = build_embedding_provider(
        provider="openai",
        openai_api_key=None,
        embedding_model="text-embedding-3-small",
    )

    assert isinstance(provider, HashEmbeddingProvider)
