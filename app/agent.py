from __future__ import annotations

from app.config import Settings
from app.escalation import (
    build_payload,
    detect_direct_trigger,
    detect_high_intent,
    last_user_text,
    send_or_log_escalation,
)
from app.models import ChatRequest, ReadinessSnapshot, SourceConfidence, StratumResult
from app.prompts import (
    CONFIDENCE_ESCALATION_MESSAGE,
    ESCALATION_SLA_MESSAGE,
    HIGH_INTENT_ESCALATION_MESSAGE,
    INTAKE_QUESTIONS,
    SCOPE_BOUNDARY_MESSAGE,
)
from app.rag import HybridRetriever


class StratumAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retriever = HybridRetriever(
            settings.knowledge_base_dir,
            confidence_threshold=settings.confidence_threshold,
        )
        self.low_confidence_counts: dict[str, int] = {}

    async def respond(self, request: ChatRequest) -> StratumResult:
        text = last_user_text(request.messages)
        direct_trigger = detect_direct_trigger(text)
        if direct_trigger or request.mode == "escalation":
            return await self._escalate(request, direct_trigger or "explicit")

        if request.mode == "intake":
            return await self._intake(request)
        if request.mode == "about":
            return self._about()
        return await self._open(request)

    async def _open(self, request: ChatRequest) -> StratumResult:
        query = last_user_text(request.messages)
        if self._is_out_of_scope(query):
            return StratumResult(
                phases=["searching", "composing"],
                response_text=SCOPE_BOUNDARY_MESSAGE,
                source=SourceConfidence(label="", score=0.0, grounded=False),
            )

        retrieval = self.retriever.retrieve(query)
        if not retrieval.source.grounded:
            count = self.low_confidence_counts.get(request.session_id, 0) + 1
            self.low_confidence_counts[request.session_id] = count
            if count >= 2:
                result = await self._escalate(request, "confidence")
                result.phases = ["searching", "retrieving", "escalating"]
                result.source = retrieval.source
                return result
            return StratumResult(
                phases=["searching", "retrieving", "composing"],
                source=retrieval.source,
                response_text=(
                    f"{CONFIDENCE_ESCALATION_MESSAGE} I do not have a strong enough "
                    "source in the EdStratum knowledge base to answer that confidently."
                ),
            )

        self.low_confidence_counts[request.session_id] = 0
        context = "\n\n".join(doc.content for doc in retrieval.docs[:3])
        response = self._grounded_response(query, retrieval.source, context)
        return StratumResult(
            phases=["searching", "retrieving", "composing"],
            source=retrieval.source,
            response_text=response,
        )

    async def _intake(self, request: ChatRequest) -> StratumResult:
        index = request.intake_index if request.intake_index is not None else 0
        if len(request.intake_answers) >= len(INTAKE_QUESTIONS) or index >= len(INTAKE_QUESTIONS):
            snapshot = self._snapshot(request)
            high_intent = detect_high_intent(request)
            response = (
                "Here is your AI Readiness Snapshot.\n\n"
                f"### Your Situation\n{snapshot.situation}\n\n"
                f"### Relevant EdStratum Capabilities\n{snapshot.capabilities}\n\n"
                f"### Realistic First Step\n{snapshot.firstStep}"
            )
            trigger = "high_intent" if high_intent else None
            if high_intent:
                response = f"{response}\n\n{HIGH_INTENT_ESCALATION_MESSAGE}"
                await self._notify_only(request, "high_intent", snapshot)
            return StratumResult(
                phases=["assessing", "composing"],
                response_text=response,
                snapshot=snapshot,
                escalate=trigger,
            )

        question = INTAKE_QUESTIONS[index]
        options = question.get("options") or []
        options_text = ""
        if options:
            options_text = "\n\nOptions: " + " / ".join(options)
        acknowledgement = "Got it." if index == 0 else "Thanks, that helps narrow the context."
        return StratumResult(
            phases=["assessing", "composing"],
            response_text=f"{acknowledgement} {question['text']}{options_text}",
        )

    def _about(self) -> StratumResult:
        return StratumResult(
            phases=["searching", "composing"],
            response_text=(
                "EdStratum Labs is a boutique, founder-led AI strategy and implementation "
                "consultancy. The operating philosophy is layered architecture: strategy, "
                "implementation, and evidence each need to support the next layer. We focus "
                "on Canvas LMS, EdTech AI integration, RAG engineering, and production AI "
                "systems that teams can maintain after launch."
            ),
        )

    async def _escalate(self, request: ChatRequest, trigger: str) -> StratumResult:
        await self._notify_only(request, trigger, None)
        message = self._handoff_message(request, trigger)
        return StratumResult(
            phases=["escalating"],
            response_text=message,
            escalate=trigger,  # type: ignore[arg-type]
        )

    async def _notify_only(
        self,
        request: ChatRequest,
        trigger: str,
        snapshot: ReadinessSnapshot | None,
    ) -> None:
        payload = build_payload(request, trigger, snapshot)
        await send_or_log_escalation(self.settings, payload)

    def _handoff_message(self, request: ChatRequest, trigger: str) -> str:
        if trigger == "confidence":
            opener = (
                "I do not have enough grounded context to answer that accurately, "
                "so this is a good moment to bring Jeffrey in."
            )
        elif trigger == "sentiment":
            opener = (
                "I may not be meeting the need cleanly here, so I am going to route this "
                "to Jeffrey with the context rather than keep guessing."
            )
        elif trigger == "high_intent":
            opener = (
                "Based on what you shared, this looks like it may be a strong fit for "
                "a focused EdStratum conversation."
            )
        else:
            opener = "Absolutely. I can connect you with Jeffrey about the project."

        return (
            f"{opener}\n\n{ESCALATION_SLA_MESSAGE}\n\n"
            f"In the meantime, here is his calendar: {self.settings.calendly_url}"
        )

    def _snapshot(self, request: ChatRequest) -> ReadinessSnapshot:
        answers = request.intake_answers
        org = answers.get("org-type") or "your organization"
        canvas = answers.get("canvas-usage") or "your current learning platform context"
        problem = answers.get("problem") or "the AI problem you described"
        data = answers.get("data-infra") or answers.get("data-quality") or "your current data foundation"
        engineering = answers.get("engineering") or "your delivery capacity"
        timeline = answers.get("timeline") or "your target timeline"

        return ReadinessSnapshot(
            situation=(
                f"You are evaluating AI for {org}, with Canvas usage described as "
                f"{canvas}. The main problem is {problem}, and the feasibility depends "
                f"heavily on {data} plus {engineering}."
            ),
            capabilities=(
                "The most relevant EdStratum capabilities are AI Implementation Strategy "
                "for roadmap and ROI discipline, plus Canvas Integration or RAG Engineering "
                "if the work needs LMS data, LTI tooling, or grounded knowledge retrieval."
            ),
            firstStep=(
                f"We would start with a short discovery audit against the {timeline} "
                "timeline: confirm data access, identify the first workflow worth automating, "
                "and define a measurable pilot before writing production code."
            ),
        )

    def _grounded_response(
        self,
        query: str,
        source: SourceConfidence,
        context: str,
    ) -> str:
        lowered = query.lower()
        if "canvas" in lowered or "lti" in lowered:
            return (
                f"Based on {source.label}, AI can make sense in a Canvas environment when "
                "there is a specific workflow to improve, such as LTI tool development, "
                "gradebook automation, roster sync, analytics, or Canvas Data pipelines. "
                "The first question is not whether AI is interesting; it is whether the "
                "Canvas data, permissions, and user workflow are stable enough to support "
                "a maintainable implementation."
            )
        if "strategy" in lowered or "roadmap" in lowered or "roi" in lowered:
            return (
                f"Based on {source.label}, we would separate AI strategy from implementation. "
                "Strategy defines the measurable use case, risk boundary, build-versus-buy "
                "decision, and evaluation method. Implementation begins only after that "
                "shape is clear enough to avoid expensive experimentation without evidence."
            )
        if "rag" in lowered or "retrieval" in lowered:
            return (
                f"Based on {source.label}, a useful RAG system needs curated source content, "
                "metadata, hybrid retrieval, reranking, evaluation questions, and a clear "
                "low-confidence behavior. STRATUM uses the same principle: grounded answers "
                "when context is present, explicit uncertainty when it is not."
            )
        return (
            f"Based on {source.label}, EdStratum is strongest when the engagement has a "
            "defined operational problem, a data or platform layer that can be inspected, "
            "and a measurable first release. The practical next step is to name the workflow, "
            "the users affected, and what evidence would prove the AI system is helping."
        )

    @staticmethod
    def _is_out_of_scope(query: str) -> bool:
        lowered = query.lower()
        scope_terms = [
            "edstratum",
            "ai",
            "canvas",
            "lti",
            "rag",
            "llm",
            "learning",
            "edtech",
            "strategy",
            "implementation",
            "workflow",
            "engagement",
            "process",
            "services",
            "project",
            "data",
            "jeffrey",
        ]
        return not any(term in lowered for term in scope_terms)
