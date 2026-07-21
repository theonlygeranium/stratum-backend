"""Deterministic scope boundary for STRATUM."""
from __future__ import annotations

from app.rag.hybrid import _query_service_areas

STRATUM_SERVICE_AREAS = {"canvas", "rag_engineering", "ai_strategy", "general"}


def is_likely_in_scope(query: str) -> bool:
    """Return true when a query maps to EdStratum's service surface."""
    query_lower = query.lower().strip()
    if not query_lower:
        return False

    general_terms = {
        "edstratum",
        "stratum",
        "contact",
        "about",
        "help",
        "hello",
        "hi ",
        "hey",
        "pricing",
        "cost",
        "price",
        "quote",
        "demo",
        "consult",
        "consultation",
        "strategy",
        "artificial intelligence",
        "ai feature",
        "ai handoff",
        "ai is the right tool",
        "build versus buy",
        "build vs buy",
        "project",
        "service",
        "services",
        "team",
        "founder",
        "leadership",
        "connect",
        "talk to",
        "speak to",
        "get in touch",
        "roadmap",
        "implementation",
        "maintainable ai",
        "right tool",
        "handoff",
        "workflow",
    }
    if any(term in query_lower for term in general_terms):
        return True

    detected_areas = _query_service_areas(query)
    return bool(detected_areas & STRATUM_SERVICE_AREAS)
