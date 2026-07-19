---
source_title: "STRATUM RAG Methodology"
source_url: "STRATUM_BUILD_SPECS.md"
service_area: "rag_engineering"
content_type: "methodology"
freshness_date: "2026-07-19"
topics: "rag,semantic_chunking,metadata,bm25,hybrid_retrieval,rrf,reranking,confidence,grounding,evaluation"
---

# RAG Methodology

STRATUM answers should be grounded in a maintained knowledge base. Retrieval uses metadata, semantic chunking, keyword search, vector-style semantic matching, reciprocal rank fusion, and reranking where available. Each answer that draws from the knowledge base must surface a source confidence badge.

When confidence is low, STRATUM must not fabricate. The correct behavior is to say that the topic should be confirmed with Jeffrey and offer escalation. This low-confidence behavior is part of EdStratum's evidence-driven brand promise.

## Chunking and Metadata

Chunks should preserve conceptual boundaries such as service sections, methodology steps, implementation notes, and evaluation rubrics. Fixed-token splitting is a fallback for oversized sections, not the primary strategy. Every chunk needs service_area, content_type, freshness_date, source_title, source_url, and chunk_index metadata so retrieval can filter before ranking and cite the selected source afterward.

## Hybrid Retrieval and Reranking

Keyword retrieval catches exact technical language such as BM25, LTI, Developer Key, Assignment and Grade Services, or Canvas Data 2. Semantic retrieval catches related intent such as "grounded answer quality," "grade passback," or "AI roadmap." Reciprocal rank fusion should combine both branches before reranking. Reranking should prefer chunks that match the query intent, service area, source type, and important phrases.

## Confidence Behavior

The confidence score should come from the best reranked chunk. A grounded response can use the chunk and cite its source label. A low-confidence response should not stretch a weak match into a definitive answer. STRATUM should say that it does not have enough specific source context and offer to connect the visitor with Jeffrey.

## Evaluation

Representative tests should cover Canvas integrations, AI roadmap questions, RAG engineering, intake completion, high-intent routing, direct escalation, frustration escalation, and out-of-scope messages.
