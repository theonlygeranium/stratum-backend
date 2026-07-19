from __future__ import annotations

from collections.abc import AsyncGenerator

from app.config import Settings
from app.escalation import (
    build_payload,
    detect_high_intent,
    detect_direct_trigger,
    last_user_text,
    send_or_log_escalation,
)
from app.graph import build_stratum_graph, procedural_fallback
from app.llm import generate_response, stream_response
from app.models import (
    ChatRequest,
    DoneEvent,
    PhaseEvent,
    ReadinessSnapshot,
    SourceConfidence,
    SourceEvent,
    StratumResult,
    StreamEvent,
    TokenEvent,
)
from app.prompts import (
    CONFIDENCE_ESCALATION_MESSAGE,
    ESCALATION_SLA_MESSAGE,
    HIGH_INTENT_ESCALATION_MESSAGE,
    INTAKE_QUESTIONS,
    RAG_SYSTEM_PROMPT,
    SCOPE_BOUNDARY_MESSAGE,
)
from app.rag import HybridRetriever
from app.session_store import SessionStore
from app.sse import token_chunks


class StratumAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retriever = HybridRetriever(
            settings.knowledge_base_dir,
            confidence_threshold=settings.confidence_threshold,
            embedding_provider=settings.embedding_provider,
            embedding_model=settings.embedding_model,
            embedding_api_key=settings.llm_api_key,
            vector_store_provider=settings.vector_store_provider,
            chroma_persist_dir=settings.chroma_persist_dir,
            reranker_provider=settings.reranker_provider,
            reranker_model=settings.reranker_model,
            cohere_api_key=settings.cohere_api_key,
        )
        self.session_store = SessionStore(settings.database_url)
        self.low_confidence_counts = self.session_store.memory_counts
        self.graph_runtime = build_stratum_graph(
            database_url=settings.database_url,
            open_handler=self._open,
            intake_handler=self._intake,
            about_handler=self._about,
            escalation_handler=self._escalate,
        )

    async def respond(self, request: ChatRequest) -> StratumResult:
        if self.graph_runtime is not None:
            return await self.graph_runtime.respond(request)
        return await procedural_fallback(
            request,
            open_handler=self._open,
            intake_handler=self._intake,
            about_handler=self._about,
            escalation_handler=self._escalate,
        )

    async def stream(self, request: ChatRequest) -> AsyncGenerator[StreamEvent, None]:
        query = last_user_text(request.messages)
        direct_trigger = detect_direct_trigger(query)
        if direct_trigger or request.mode == "escalation":
            async for event in self._stream_escalation(
                request,
                direct_trigger or "explicit",
            ):
                yield event
            return

        if request.mode == "intake":
            async for event in self._stream_result(await self._intake(request)):
                yield event
            return

        if request.mode == "about":
            async for event in self._stream_result(self._about()):
                yield event
            return

        async for event in self._stream_open(request):
            yield event

    async def _stream_open(
        self,
        request: ChatRequest,
    ) -> AsyncGenerator[StreamEvent, None]:
        query = last_user_text(request.messages)
        yield PhaseEvent(type="phase", phase="searching")

        if self._is_out_of_scope(query):
            yield PhaseEvent(type="phase", phase="composing")
            source = SourceConfidence(label="", score=0.0, grounded=False)
            yield SourceEvent(type="source", source=source)
            async for event in self._stream_text(SCOPE_BOUNDARY_MESSAGE):
                yield event
            yield DoneEvent(type="done")
            return

        yield PhaseEvent(type="phase", phase="retrieving")
        retrieval = self.retriever.retrieve(query)

        if not retrieval.source.grounded:
            count = await self.session_store.get_low_confidence_count(
                request.session_id
            ) + 1
            await self.session_store.set_low_confidence_count(request.session_id, count)
            if count >= 2:
                yield PhaseEvent(type="phase", phase="escalating")
                await self._notify_only(request, "confidence", None)
                yield SourceEvent(type="source", source=retrieval.source)
                async for event in self._stream_text(
                    self._handoff_message(request, "confidence")
                ):
                    yield event
                yield DoneEvent(type="done", escalate="confidence")
                return

            yield PhaseEvent(type="phase", phase="composing")
            yield SourceEvent(type="source", source=retrieval.source)
            async for event in self._stream_text(
                f"{CONFIDENCE_ESCALATION_MESSAGE} I do not have a strong enough "
                "source in the EdStratum knowledge base to answer that confidently. "
                f"If you'd like to discuss this with Jeffrey, you can book a call here: "
                f"{self.settings.calendly_url}"
            ):
                yield event
            yield DoneEvent(type="done")
            return

        await self.session_store.set_low_confidence_count(request.session_id, 0)
        yield PhaseEvent(type="phase", phase="composing")
        yield SourceEvent(type="source", source=retrieval.source)
        context = "\n\n".join(doc.content for doc in retrieval.docs[:3])

        streamed = False
        async for token in self._stream_grounded_response(
            query,
            retrieval.source,
            context,
            request,
        ):
            streamed = True
            yield TokenEvent(type="token", token=token)

        if not streamed:
            response = self._context_fallback(query, retrieval.source, context)
            async for event in self._stream_text(response):
                yield event

        yield DoneEvent(type="done")

    async def _stream_escalation(
        self,
        request: ChatRequest,
        trigger: str,
    ) -> AsyncGenerator[StreamEvent, None]:
        yield PhaseEvent(type="phase", phase="escalating")
        await self._notify_only(request, trigger, None)
        async for event in self._stream_text(self._handoff_message(request, trigger)):
            yield event
        yield DoneEvent(type="done", escalate=trigger)  # type: ignore[arg-type]

    async def _stream_result(
        self,
        result: StratumResult,
    ) -> AsyncGenerator[StreamEvent, None]:
        for phase in result.phases:
            yield PhaseEvent(type="phase", phase=phase)
        if result.source is not None:
            yield SourceEvent(type="source", source=result.source)
        async for event in self._stream_text(result.response_text):
            yield event
        yield DoneEvent(
            type="done",
            snapshot=result.snapshot,
            escalate=result.escalate,
        )

    async def _stream_text(self, text: str) -> AsyncGenerator[TokenEvent, None]:
        for token in token_chunks(text):
            yield TokenEvent(type="token", token=token)

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
            count = await self.session_store.get_low_confidence_count(request.session_id) + 1
            await self.session_store.set_low_confidence_count(request.session_id, count)
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
                    "source in the EdStratum knowledge base to answer that confidently. "
                    f"If you'd like to discuss this with Jeffrey, you can book a call here: "
                    f"{self.settings.calendly_url}"
                ),
            )

        await self.session_store.set_low_confidence_count(request.session_id, 0)
        context = "\n\n".join(doc.content for doc in retrieval.docs[:3])
        response = await self._grounded_response(query, retrieval.source, context, request)
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

    async def _grounded_response(
        self,
        query: str,
        source: SourceConfidence,
        context: str,
        request: ChatRequest,
    ) -> str:
        """Generate a grounded response using the LLM, with a fallback.

        The LLM receives the retrieved context and recent conversation history
        so it can answer naturally and reference prior turns. If the LLM call
        fails or no API key is configured, we fall back to a concise summary
        of the retrieved context rather than a keyword-matched template.
        """
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
            if msg.role in ("user", "assistant") and msg.content
        ]

        # Inject the calendar URL into the system prompt so the LLM can
        # provide it when visitors ask about scheduling or contacting Jeffrey.
        system_prompt = RAG_SYSTEM_PROMPT.format(
            calendar_url=self.settings.calendly_url
        )

        llm_response = await generate_response(
            self.settings,
            system_prompt,
            context,
            conversation_history,
            query,
        )

        if llm_response:
            return llm_response

        # Fallback: summarize the retrieved context directly.
        # This is used only when the LLM is unavailable.
        return self._context_fallback(query, source, context)

    async def _stream_grounded_response(
        self,
        query: str,
        source: SourceConfidence,
        context: str,
        request: ChatRequest,
    ) -> AsyncGenerator[str, None]:
        del source
        conversation_history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
            if msg.role in ("user", "assistant") and msg.content
        ]
        system_prompt = RAG_SYSTEM_PROMPT.format(
            calendar_url=self.settings.calendly_url
        )
        async for token in stream_response(
            self.settings,
            system_prompt,
            context,
            conversation_history,
            query,
        ):
            yield token

    def _context_fallback(
        self,
        query: str,
        source: SourceConfidence,
        context: str,
    ) -> str:
        """Produce a readable answer from retrieved context when the LLM is down.

        Extracts the first substantive paragraph from the context and presents
        it with the source attribution. This is a degraded mode — not as good
        as the LLM response, but far better than the old keyword-matched templates.
        """
        # Take the first 400 chars of the context as the answer body
        body = context.strip()
        if len(body) > 400:
            # Cut at the last sentence boundary within 400 chars
            cut = body[:400].rsplit(".", 1)
            if len(cut) == 2:
                body = cut[0] + "."
            else:
                body = body[:400].rstrip() + "…"

        return f"Based on {source.label}:\n\n{body}"

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
            "service",
            "project",
            "data",
            "jeffrey",
            "methodology",
            "roadmap",
            "roi",
            "analytics",
            "automation",
            "integration",
            "consult",
            "professional",
            "offer",
            "what do you do",
            "what does",
            "tell me about",
            "about",
            "help",
            "how do",
            "can you",
            "contact",
            "schedule",
            "call",
            "meeting",
            "talk",
            "speak",
            "connect",
            "pricing",
            "cost",
            "hire",
            "work with",
            "engage",
            "consultation",
            "discovery",
        ]
        return not any(term in lowered for term in scope_terms)
