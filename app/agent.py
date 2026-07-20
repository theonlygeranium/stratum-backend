from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from typing import Any

from app.config import Settings
from app.escalation import (
    build_payload,
    detect_high_intent,
    last_user_text,
    send_or_log_escalation,
)
from app.graph import (
    StratumState,
    build_stratum_graph,
    initial_state_from_request,
    procedural_fallback,
    request_from_state,
    route_key,
    route_node,
    state_update_from_result,
)
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
    ESCALATION_PREPARED_MESSAGE,
    ESCALATION_SLA_MESSAGE,
    HIGH_INTENT_ESCALATION_MESSAGE,
    INTAKE_QUESTIONS,
    RAG_SYSTEM_PROMPT,
    SCOPE_BOUNDARY_MESSAGE,
)
from app.rag import HybridRetriever
from app.session_store import SessionStore
from app.sse import token_chunks


_SUPPRESS_NOTIFICATIONS: ContextVar[bool] = ContextVar(
    "stratum_suppress_notifications",
    default=False,
)
GROUNDING_PREAMBLE = "Here is the grounded read: "


class StratumAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.retriever = HybridRetriever(
            settings.knowledge_base_dir,
            confidence_threshold=settings.confidence_threshold,
            embedding_provider=settings.embedding_provider,
            embedding_model=settings.embedding_model,
            embedding_api_key=settings.openai_api_key,
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
            open_handler=self._prepare_open,
            intake_handler=self._intake,
            about_handler=self._about,
            escalation_handler=self._escalate,
            generate_handler=self._generate_open_from_state,
        )

    def runtime_status(self) -> dict[str, Any]:
        graph_runtime_name = (
            "langgraph" if self.graph_runtime is not None else "procedural"
        )
        checkpointer_name = (
            self.graph_runtime.checkpointer_name
            if self.graph_runtime is not None
            else "none"
        )
        return {
            "status": "online",
            "graph_runtime": graph_runtime_name,
            "checkpointer": checkpointer_name,
            "database_configured": bool(self.settings.database_url),
            "session_store_backend": self.session_store.backend_name,
            "session_store_database_disabled": self.session_store.database_disabled,
            "embedding_provider": self.retriever.embedding_provider,
            "vector_store_provider": self.retriever.vector_store_provider,
            "reranker_provider": self.retriever.reranker_provider,
            "reranker_model": self.retriever.reranker_model,
            "llm_configured": bool(self.settings.llm_api_key),
            "llm_provider": self.settings.llm_provider,
            "llm_base_url": self.settings.llm_base_url,
            "llm_model": self.settings.llm_model,
            "writer_api_key_configured": bool(self.settings.writer_api_key),
            "openai_api_key_configured": bool(self.settings.openai_api_key),
            "resend_configured": bool(self.settings.resend_api_key),
            "escalation_email_configured": bool(self.settings.jeffrey_email),
            "notifications_configured": bool(
                self.settings.resend_api_key and self.settings.jeffrey_email
            ),
            "allowed_origins_env_configured": os.getenv("ALLOWED_ORIGINS") is not None,
        }

    async def respond(
        self,
        request: ChatRequest,
        *,
        suppress_notifications: bool = False,
    ) -> StratumResult:
        token = _SUPPRESS_NOTIFICATIONS.set(suppress_notifications)
        try:
            if self.graph_runtime is not None:
                return await self.graph_runtime.respond(request)
            return await procedural_fallback(
                request,
                open_handler=self._open,
                intake_handler=self._intake,
                about_handler=self._about,
                escalation_handler=self._escalate,
            )
        finally:
            _SUPPRESS_NOTIFICATIONS.reset(token)

    async def stream(
        self,
        request: ChatRequest,
        *,
        suppress_notifications: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        state = initial_state_from_request(request)
        state.update(route_node(state))
        mode = route_key(state)

        if mode != "open":
            async for event in self._stream_result(
                await self.respond(
                    request,
                    suppress_notifications=suppress_notifications,
                )
            ):
                yield event
            return

        async for event in self._stream_open(
            request_from_state(state),
            suppress_notifications=suppress_notifications,
        ):
            yield event

    async def _stream_open(
        self,
        request: ChatRequest,
        *,
        suppress_notifications: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        if self.graph_runtime is not None:
            async for event in self._stream_open_graph(
                request,
                suppress_notifications=suppress_notifications,
            ):
                yield event
            return

        async for event in self._stream_open_direct(
            request,
            suppress_notifications=suppress_notifications,
        ):
            yield event

    async def _stream_open_graph(
        self,
        request: ChatRequest,
        *,
        suppress_notifications: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        token = _SUPPRESS_NOTIFICATIONS.set(suppress_notifications)
        try:
            async for node_name, update in self.graph_runtime.stream_updates(
                request,
                interrupt_after=["open"],
            ):
                if node_name != "open":
                    continue
                result_payload = update.get("result")
                if result_payload:
                    async for event in self._stream_result(
                        StratumResult.model_validate(result_payload)
                    ):
                        yield event
                    return

                source_payload = update.get("source_confidence")
                if not source_payload:
                    raise ValueError("STRATUM graph open node did not return a source")

                source = SourceConfidence.model_validate(source_payload)
                context = self._retrieved_context_text(update)
                query = last_user_text(request.messages)

                yield PhaseEvent(type="phase", phase="searching")
                yield PhaseEvent(type="phase", phase="retrieving")
                yield PhaseEvent(type="phase", phase="composing")
                yield SourceEvent(type="source", source=source)

                chunks: list[str] = [GROUNDING_PREAMBLE]
                yield TokenEvent(type="token", token=GROUNDING_PREAMBLE)
                async for chunk in self._stream_grounded_response(
                    query,
                    source,
                    context,
                    request,
                ):
                    chunks.append(chunk)
                    yield TokenEvent(type="token", token=chunk)

                response = "".join(chunks)
                if not response:
                    response = self._context_fallback(query, source, context)
                    async for event in self._stream_text(response):
                        yield event

                await self.graph_runtime.checkpoint_result(
                    request,
                    StratumResult(
                        phases=["searching", "retrieving", "composing"],
                        source=source,
                        response_text=response,
                    ),
                )
                yield DoneEvent(type="done")
                return

            raise ValueError("STRATUM graph stream ended before open node")
        finally:
            _SUPPRESS_NOTIFICATIONS.reset(token)

    async def _stream_open_direct(
        self,
        request: ChatRequest,
        *,
        suppress_notifications: bool = False,
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
                notification_sent = False
                if not suppress_notifications:
                    notification_sent = await self._notify_only(
                        request,
                        "confidence",
                        None,
                    )
                yield SourceEvent(type="source", source=retrieval.source)
                async for event in self._stream_text(
                    self._handoff_message(
                        request,
                        "confidence",
                        notification_sent=notification_sent,
                    )
                ):
                    yield event
                yield DoneEvent(type="done", escalate="confidence")
                return

            yield PhaseEvent(type="phase", phase="composing")
            yield SourceEvent(type="source", source=retrieval.source)
            async for event in self._stream_text(
                f"{CONFIDENCE_ESCALATION_MESSAGE} I do not have a strong enough "
                "source in the EdStratum knowledge base to answer that confidently. "
                "If you'd like, I can route this to the Founding leadership team."
            ):
                yield event
            yield DoneEvent(type="done")
            return

        await self.session_store.set_low_confidence_count(request.session_id, 0)
        yield PhaseEvent(type="phase", phase="composing")
        yield SourceEvent(type="source", source=retrieval.source)
        context = "\n\n".join(doc.content for doc in retrieval.docs[:3])
        yield TokenEvent(type="token", token=GROUNDING_PREAMBLE)

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
        prepared = await self._prepare_open(request)
        result_payload = prepared.get("result")
        if result_payload:
            return StratumResult.model_validate(result_payload)
        return await self._generate_open_from_update(request, prepared)

    async def _prepare_open(self, request: ChatRequest) -> dict[str, Any]:
        query = last_user_text(request.messages)
        if self._is_out_of_scope(query):
            return state_update_from_result(
                StratumResult(
                    phases=["searching", "composing"],
                    response_text=SCOPE_BOUNDARY_MESSAGE,
                    source=SourceConfidence(label="", score=0.0, grounded=False),
                )
            )

        retrieval = self.retriever.retrieve(query)
        if not retrieval.source.grounded:
            count = (
                await self.session_store.get_low_confidence_count(request.session_id)
                + 1
            )
            await self.session_store.set_low_confidence_count(request.session_id, count)
            if count >= 2:
                result = await self._escalate(request, "confidence")
                result.phases = ["searching", "retrieving", "escalating"]
                result.source = retrieval.source
                return state_update_from_result(result)
            return state_update_from_result(
                StratumResult(
                    phases=["searching", "retrieving", "composing"],
                    source=retrieval.source,
                    response_text=(
                        f"{CONFIDENCE_ESCALATION_MESSAGE} I do not have a strong enough "
                        "source in the EdStratum knowledge base to answer that confidently. "
                        "If you'd like, I can route this to the Founding leadership team."
                    ),
                )
            )

        await self.session_store.set_low_confidence_count(request.session_id, 0)
        return {
            "retrieved_context": [doc.content for doc in retrieval.docs[:3]],
            "source_confidence": retrieval.source.model_dump(mode="json"),
            "response_text": "",
            "result": None,
        }

    async def _generate_open_from_state(
        self,
        state: StratumState,
    ) -> StratumResult:
        return await self._generate_open_from_update(request_from_state(state), state)

    async def _generate_open_from_update(
        self,
        request: ChatRequest,
        update: dict[str, Any],
    ) -> StratumResult:
        source_payload = update.get("source_confidence")
        if not source_payload:
            result_payload = update.get("result")
            if result_payload:
                return StratumResult.model_validate(result_payload)
            raise ValueError("STRATUM open generation missing source confidence")

        query = last_user_text(request.messages)
        source = SourceConfidence.model_validate(source_payload)
        context = self._retrieved_context_text(update)
        response = await self._grounded_response(query, source, context, request)
        return StratumResult(
            phases=["searching", "retrieving", "composing"],
            source=source,
            response_text=response,
        )

    @staticmethod
    def _retrieved_context_text(update: dict[str, Any]) -> str:
        return "\n\n".join(str(item) for item in update.get("retrieved_context") or [])

    async def _intake(
        self,
        request: ChatRequest,
        *,
        suppress_notifications: bool = False,
    ) -> StratumResult:
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
                if not (
                    suppress_notifications or _SUPPRESS_NOTIFICATIONS.get()
                ):
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
        notification_sent = False
        if not _SUPPRESS_NOTIFICATIONS.get():
            notification_sent = await self._notify_only(request, trigger, None)
        message = self._handoff_message(
            request,
            trigger,
            notification_sent=notification_sent,
        )
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
    ) -> bool:
        payload = build_payload(request, trigger, snapshot)
        return await send_or_log_escalation(self.settings, payload)

    def _handoff_message(
        self,
        request: ChatRequest,
        trigger: str,
        *,
        notification_sent: bool,
    ) -> str:
        if trigger == "confidence":
            opener = (
                "I do not have enough grounded context to answer that accurately, "
                "so this is a good moment to bring in EdStratum's Founding leadership team."
            )
        elif trigger == "sentiment":
            opener = (
                "I may not be meeting the need cleanly here, so I am going to route this "
                "to the Founding leadership team with the context rather than keep guessing."
            )
        elif trigger == "high_intent":
            opener = (
                "Based on what you shared, this looks like it may be a strong fit for "
                "a focused EdStratum conversation."
            )
        else:
            opener = (
                "Absolutely. I can connect you with EdStratum's Founding leadership team "
                "about the project."
            )

        notification_copy = (
            ESCALATION_SLA_MESSAGE
            if notification_sent
            else ESCALATION_PREPARED_MESSAGE
        )
        parts = [opener, notification_copy]
        if self.settings.calendly_url:
            parts.append(
                f"You can also use this scheduling link: {self.settings.calendly_url}"
            )
        return "\n\n".join(parts)

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

        system_prompt = RAG_SYSTEM_PROMPT.format()

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
        system_prompt = RAG_SYSTEM_PROMPT.format()
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
            "advising",
            "assessment",
            "bm25",
            "chunking",
            "integration",
            "grounding",
            "grounded",
            "hybrid",
            "pilot",
            "consult",
            "professional",
            "offer",
            "retrieval",
            "semantic",
            "source confidence",
            "triage",
            "vendor",
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
