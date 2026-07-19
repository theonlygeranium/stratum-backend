from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.models import SourceConfidence
from app.rag.chunker import chunk_documents
from app.rag.documents import Document, load_knowledge_base


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.+#-]*")
STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "have",
    "how",
    "i",
    "if",
    "in",
    "is",
    "it",
    "my",
    "need",
    "of",
    "on",
    "or",
    "our",
    "should",
    "that",
    "the",
    "their",
    "there",
    "this",
    "to",
    "we",
    "what",
    "when",
    "where",
    "with",
    "would",
}

SERVICE_AREA_TERMS = {
    "canvas": {
        "ags",
        "assignment",
        "canvas",
        "course",
        "developer key",
        "enrollment",
        "external tool",
        "grade",
        "gradebook",
        "instructure",
        "launch",
        "lms",
        "lti",
        "nrps",
        "oauth",
        "placement",
        "roster",
        "sso",
        "submission",
    },
    "rag_engineering": {
        "bm25",
        "chunk",
        "citation",
        "confidence",
        "embedding",
        "grounded",
        "hallucination",
        "hybrid",
        "knowledge base",
        "rag",
        "rerank",
        "retrieval",
        "rrf",
        "semantic",
        "source",
        "vector",
    },
    "ai_strategy": {
        "audit",
        "build-versus-buy",
        "compliance",
        "cost",
        "discovery",
        "evaluation",
        "governance",
        "policy",
        "pilot",
        "roadmap",
        "roi",
        "strategy",
        "tco",
        "vendor",
    },
}

CONTENT_TYPE_TERMS = {
    "case_study": {"case", "example", "outcome", "pattern", "proof"},
    "intake_logic": {"assessment", "intake", "question", "readiness", "rubric", "score"},
    "methodology": {"framework", "method", "methodology", "process"},
    "service": {"capability", "service", "work"},
    "technical_doc": {"api", "developer", "implementation", "lti", "technical"},
}

TOKEN_CONCEPTS = {
    "ags": {"assignment_grade_service", "gradebook", "lti_advantage"},
    "analytics": {"measurement", "learning_analytics", "evidence"},
    "api": {"integration", "technical"},
    "assessment": {"intake", "readiness", "evaluation"},
    "bm25": {"keyword_search", "hybrid_retrieval", "rag"},
    "canvas": {"canvas", "lms", "instructure"},
    "chunk": {"semantic_chunking", "rag"},
    "citation": {"source_confidence", "grounding"},
    "compliance": {"governance", "risk"},
    "cost": {"tco", "roi"},
    "data": {"evidence", "source", "integration"},
    "embedding": {"semantic_search", "vector", "rag"},
    "evaluation": {"measurement", "roi", "rubric"},
    "gradebook": {"grades", "assignment_grade_service", "canvas"},
    "grounded": {"source_confidence", "evidence", "rag"},
    "hallucination": {"low_confidence", "grounding", "risk"},
    "hybrid": {"bm25", "semantic_search", "rag"},
    "instructure": {"canvas", "lms"},
    "launch": {"lti", "external_tool", "oauth"},
    "llm": {"ai", "model"},
    "lms": {"canvas", "learning_management_system"},
    "lti": {"external_tool", "lti_advantage", "canvas"},
    "nrps": {"names_roles", "roster", "lti_advantage"},
    "oauth": {"developer_key", "security", "canvas"},
    "pilot": {"first_release", "evaluation", "roadmap"},
    "policy": {"governance", "risk"},
    "rag": {"retrieval", "grounding", "knowledge_base"},
    "rerank": {"cross_encoder", "relevance", "rag"},
    "retrieval": {"search", "grounding", "rag"},
    "roadmap": {"strategy", "prioritization", "planning"},
    "roster": {"enrollment", "names_roles", "canvas"},
    "roi": {"measurement", "business_case", "value"},
    "rrf": {"reciprocal_rank_fusion", "hybrid_retrieval"},
    "sso": {"identity", "authentication", "canvas"},
    "strategy": {"roadmap", "planning", "prioritization"},
    "tco": {"cost", "business_case"},
    "vector": {"semantic_search", "embedding", "rag"},
    "vendor": {"build_buy", "procurement"},
}

PHRASE_CONCEPTS = {
    "assignment and grade services": {"ags", "gradebook", "lti_advantage"},
    "build versus buy": {"build_buy", "vendor", "strategy"},
    "build-versus-buy": {"build_buy", "vendor", "strategy"},
    "canvas data": {"canvas_data", "analytics", "evidence"},
    "canvas data 2": {"canvas_data", "analytics", "pipeline"},
    "developer key": {"developer_key", "oauth", "canvas"},
    "external tool": {"external_tool", "lti", "canvas"},
    "knowledge base": {"knowledge_base", "rag", "grounding"},
    "lti 1.3": {"lti_advantage", "external_tool", "canvas"},
    "lti advantage": {"lti_advantage", "external_tool", "canvas"},
    "names and role": {"names_roles", "roster", "lti_advantage"},
    "source confidence": {"source_confidence", "grounding", "rag"},
}


@dataclass(frozen=True)
class RetrievalResult:
    docs: list[Document]
    source: SourceConfidence


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class HybridRetriever:
    def __init__(self, knowledge_base_dir: Path, confidence_threshold: float = 0.55):
        docs = load_knowledge_base(knowledge_base_dir)
        self.docs = chunk_documents(docs)
        self.confidence_threshold = confidence_threshold
        self._doc_text = [_document_search_text(doc) for doc in self.docs]
        self._doc_tokens = [tokenize(text) for text in self._doc_text]
        self._doc_terms = [_content_terms(tokens) for tokens in self._doc_tokens]
        self._doc_term_counts = [Counter(tokens) for tokens in self._doc_tokens]
        self._avgdl = (
            sum(len(tokens) for tokens in self._doc_tokens) / len(self._doc_tokens)
            if self._doc_tokens
            else 0.0
        )
        self._idf = self._build_idf()
        self._doc_feature_counts = [
            _semantic_features(text, doc.metadata) for text, doc in zip(self._doc_text, self.docs)
        ]
        self._feature_idf = self._build_feature_idf()
        self._doc_vectors = [self._feature_vector(counts) for counts in self._doc_feature_counts]

    def retrieve(self, query: str, top_k: int = 5) -> RetrievalResult:
        if not self.docs or not query.strip():
            return RetrievalResult(
                docs=[],
                source=SourceConfidence(label="", score=0.0, grounded=False),
            )

        candidate_indexes = self._metadata_filter(query)
        candidate_limit = max(top_k * 4, 10)
        bm25 = self._rank_bm25(query, candidate_indexes)[:candidate_limit]
        semantic = self._rank_semantic(query, candidate_indexes)[:candidate_limit]
        fused = self._rrf_fusion([bm25, semantic], weights=[0.4, 0.6])
        reranked = self._rerank(query, fused[:candidate_limit], bm25, semantic)
        top = reranked[:top_k]
        docs = [self._document_with_scores(*item) for item in top]
        source = self._source_confidence(docs)
        return RetrievalResult(docs=docs, source=source)

    def _build_idf(self) -> dict[str, float]:
        idf: dict[str, float] = {}
        total = len(self._doc_tokens)
        if total == 0:
            return idf
        document_frequency: Counter[str] = Counter()
        for tokens in self._doc_tokens:
            document_frequency.update(set(tokens))
        for token, df in document_frequency.items():
            idf[token] = math.log(1 + (total - df + 0.5) / (df + 0.5))
        return idf

    def _build_feature_idf(self) -> dict[str, float]:
        idf: dict[str, float] = {}
        total = len(self._doc_feature_counts)
        if total == 0:
            return idf
        document_frequency: Counter[str] = Counter()
        for counts in self._doc_feature_counts:
            document_frequency.update(set(counts))
        for feature, df in document_frequency.items():
            idf[feature] = math.log(1 + (total - df + 0.5) / (df + 0.5))
        return idf

    def _metadata_filter(self, query: str) -> list[int]:
        areas = _query_service_areas(query)
        if not areas:
            return list(range(len(self.docs)))
        filtered = [
            index
            for index, doc in enumerate(self.docs)
            if _doc_service_areas(doc.metadata) & areas
            or doc.metadata.get("service_area") == "general"
            or _topic_overlap(tokenize(query), doc.metadata) > 0
        ]
        return filtered or list(range(len(self.docs)))

    def _rank_bm25(self, query: str, indexes: list[int]) -> list[tuple[int, float]]:
        q_tokens = tokenize(query)
        k1 = 1.5
        b = 0.75
        scores: list[tuple[int, float]] = []
        for index in indexes:
            tokens = self._doc_tokens[index]
            counts = self._doc_term_counts[index]
            dl = len(tokens) or 1
            score = 0.0
            for token in q_tokens:
                if token not in counts:
                    continue
                tf = counts[token]
                idf = self._idf.get(token, 0.0)
                denominator = tf + k1 * (1 - b + b * dl / (self._avgdl or 1))
                score += idf * (tf * (k1 + 1) / denominator)
            scores.append((index, score))
        return sorted(scores, key=lambda item: item[1], reverse=True)

    def _rank_semantic(self, query: str, indexes: list[int]) -> list[tuple[int, float]]:
        q_counts = _semantic_features(query)
        q_vector = self._feature_vector(q_counts)
        scores: list[tuple[int, float]] = []
        for index in indexes:
            scores.append((index, _cosine(q_vector, self._doc_vectors[index])))
        return sorted(scores, key=lambda item: item[1], reverse=True)

    def _feature_vector(self, counts: Counter[str]) -> dict[str, float]:
        return {
            feature: count * self._feature_idf.get(feature, 0.0)
            for feature, count in counts.items()
        }

    @staticmethod
    def _rrf_fusion(
        rankings: list[list[tuple[int, float]]],
        *,
        weights: list[float],
        k: int = 60,
    ) -> list[tuple[int, float]]:
        fused: defaultdict[int, float] = defaultdict(float)
        for ranking, weight in zip(rankings, weights, strict=True):
            for rank, (index, raw_score) in enumerate(ranking, start=1):
                if raw_score <= 0:
                    continue
                fused[index] += weight / (k + rank)
        return sorted(fused.items(), key=lambda item: (-item[1], item[0]))

    def _rerank(
        self,
        query: str,
        fused: list[tuple[int, float]],
        bm25: list[tuple[int, float]],
        semantic: list[tuple[int, float]],
    ) -> list[tuple[int, float, float, float]]:
        if not fused:
            return []

        bm25_scores = dict(bm25)
        semantic_scores = dict(semantic)
        max_bm25 = max(bm25_scores.values() or [0.0])
        reranked: list[tuple[int, float, float, float]] = []

        for index, fused_score in fused:
            bm25_norm = bm25_scores.get(index, 0.0) / max_bm25 if max_bm25 else 0.0
            semantic_score = semantic_scores.get(index, 0.0)
            relevance = self._relevance_score(
                query,
                index,
                fused_score=fused_score,
                bm25_score=bm25_norm,
                semantic_score=semantic_score,
            )
            reranked.append((index, relevance, fused_score, semantic_score))

        return sorted(reranked, key=lambda item: (-item[1], -item[2], item[0]))

    def _relevance_score(
        self,
        query: str,
        index: int,
        *,
        fused_score: float,
        bm25_score: float,
        semantic_score: float,
    ) -> float:
        query_terms = set(_content_terms(tokenize(query)))
        if not query_terms:
            return 0.0

        doc_terms = set(self._doc_terms[index])
        lexical_overlap = len(query_terms & doc_terms) / max(len(query_terms), 1)
        phrase_score = _phrase_alignment(query, self._doc_text[index])
        metadata_score = _metadata_alignment(query, self.docs[index].metadata)
        retrieval_score = min(1.0, fused_score * 55)

        score = (
            semantic_score * 0.34
            + lexical_overlap * 0.24
            + bm25_score * 0.14
            + phrase_score * 0.12
            + metadata_score * 0.10
            + retrieval_score * 0.06
        )
        return max(0.0, min(1.0, score))

    def _document_with_scores(
        self,
        index: int,
        relevance_score: float,
        fused_score: float,
        semantic_score: float,
    ) -> Document:
        doc = self.docs[index]
        metadata = dict(doc.metadata)
        metadata["relevance_score"] = round(relevance_score, 4)
        metadata["retrieval_score"] = round(fused_score, 4)
        metadata["semantic_score"] = round(semantic_score, 4)
        return Document(content=doc.content, metadata=metadata)

    def _source_confidence(self, docs: list[Document]) -> SourceConfidence:
        if not docs:
            return SourceConfidence(label="", score=0.0, grounded=False)
        doc = docs[0]
        relevance_score = float(doc.metadata.get("relevance_score", 0.0))
        score = min(1.0, relevance_score * 1.1 + 0.08)
        score = round(score, 2)
        return SourceConfidence(
            label=str(doc.metadata.get("source_title", "EdStratum Knowledge Base")),
            score=score,
            grounded=score >= self.confidence_threshold,
        )


def _document_search_text(doc: Document) -> str:
    metadata = doc.metadata
    parts = [
        doc.content,
        str(metadata.get("source_title", "")),
        str(metadata.get("section_title", "")),
        str(metadata.get("service_area", "")),
        str(metadata.get("content_type", "")),
        _metadata_list_text(metadata.get("service_areas")),
        _metadata_list_text(metadata.get("topics")),
        _metadata_list_text(metadata.get("aliases")),
    ]
    return "\n".join(part for part in parts if part)


def _metadata_list_text(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _content_terms(tokens: list[str]) -> list[str]:
    return [token for token in tokens if token not in STOPWORDS and len(token) > 1]


def _semantic_features(text: str, metadata: dict[str, object] | None = None) -> Counter[str]:
    lowered = text.lower()
    tokens = _content_terms(tokenize(lowered))
    features: Counter[str] = Counter()

    for token in tokens:
        features[token] += 1.0
        stem = _stem(token)
        if stem != token:
            features[f"stem:{stem}"] += 0.45
        for concept in TOKEN_CONCEPTS.get(token, set()):
            features[f"concept:{concept}"] += 0.85

    for left, right in zip(tokens, tokens[1:]):
        features[f"bigram:{left}_{right}"] += 0.35

    for phrase, concepts in PHRASE_CONCEPTS.items():
        if phrase in lowered:
            for concept in concepts:
                features[f"concept:{concept}"] += 1.8

    if metadata:
        for area in _doc_service_areas(metadata):
            features[f"area:{area}"] += 1.3
        content_type = str(metadata.get("content_type", "")).strip()
        if content_type:
            features[f"type:{content_type}"] += 0.9
        for topic in _metadata_values(metadata.get("topics")):
            features[f"topic:{topic.lower()}"] += 1.0

    return features


def _stem(token: str) -> str:
    for suffix in ("ization", "ations", "ation", "ments", "ment", "ing", "ies", "ed", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            if suffix == "ies":
                return f"{token[:-3]}y"
            return token[: -len(suffix)]
    return token


def _query_service_areas(query: str) -> set[str]:
    lowered = query.lower()
    tokens = set(tokenize(lowered))
    areas: set[str] = set()
    for area, terms in SERVICE_AREA_TERMS.items():
        for term in terms:
            if " " in term and term in lowered:
                areas.add(area)
                break
            if term in tokens:
                areas.add(area)
                break
    return areas


def _doc_service_areas(metadata: dict[str, object]) -> set[str]:
    areas = {str(metadata.get("service_area", "general")).strip() or "general"}
    areas.update(_metadata_values(metadata.get("service_areas")))
    return {area for area in areas if area}


def _metadata_values(value: object) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    if value:
        return {item.strip() for item in str(value).split(",") if item.strip()}
    return set()


def _topic_overlap(query_tokens: list[str], metadata: dict[str, object]) -> float:
    topics = {token for topic in _metadata_values(metadata.get("topics")) for token in tokenize(topic)}
    if not topics:
        return 0.0
    query_terms = set(_content_terms(query_tokens))
    return len(query_terms & topics) / max(len(query_terms), 1)


def _metadata_alignment(query: str, metadata: dict[str, object]) -> float:
    query_tokens = tokenize(query)
    query_terms = set(_content_terms(query_tokens))
    if not query_terms:
        return 0.0

    areas = _query_service_areas(query)
    doc_areas = _doc_service_areas(metadata)
    area_score = 0.0
    if areas & doc_areas:
        area_score = 1.0
    elif areas and "general" in doc_areas:
        area_score = 0.55

    content_type = str(metadata.get("content_type", ""))
    type_terms = CONTENT_TYPE_TERMS.get(content_type, set())
    type_score = 1.0 if query_terms & type_terms else 0.0
    topic_score = min(1.0, _topic_overlap(query_tokens, metadata) * 2.5)

    return max(area_score, type_score, topic_score)


def _phrase_alignment(query: str, document: str) -> float:
    query_terms = _content_terms(tokenize(query))
    if len(query_terms) < 2:
        return 0.0

    document_lowered = document.lower()
    matches = 0
    total = 0
    for size in (2, 3):
        for index in range(0, max(len(query_terms) - size + 1, 0)):
            total += 1
            phrase = " ".join(query_terms[index : index + size])
            if phrase in document_lowered:
                matches += 1
    if total == 0:
        return 0.0
    return matches / total


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(token, 0.0) for token, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
