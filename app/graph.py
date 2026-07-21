from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict, cast

from app.escalation import detect_direct_trigger, last_user_text
from app.models import (
    ChatRequest,
    ConversationMode,
    EscalationTrigger,
    SentimentSignal,
    StratumResult,
)
from app.prompts import INTAKE_QUESTIONS


try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover - optional dependency fallback
    MemorySaver = None  # type: ignore[assignment]
    StateGraph = None  # type: ignore[assignment]
    START = "__start__"  # type: ignore[assignment]
    END = "__end__"  # type: ignore[assignment]


def merge_frontend_messages(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Use the frontend-supplied transcript when present; otherwise keep checkpoints."""
    if right:
        return list(right)
    return list(left or [])


class StratumState(TypedDict):
    messages: Annotated[list[dict[str, Any]], merge_frontend_messages]
    mode: ConversationMode
    request_mode: ConversationMode
    intake_index: int | None
    intake_answers: dict[str, str]
    retrieved_context: list
    source_confidence: dict[str, Any] | None
    citations: list[dict[str, Any]]
    escalation_trigger: EscalationTrigger
    sentiment_signal: SentimentSignal | None
    escalation: dict[str, Any] | None
    escalation_context: dict[str, Any] | None
    response_text: str
    snapshot: dict[str, Any] | None
    session_id: str
    result: dict[str, Any] | None


VALID_ROUTE_KEYS: set[ConversationMode] = {"open", "intake", "about", "escalation"}


def initial_state_from_request(request: ChatRequest) -> StratumState:
    return {
        "messages": [
            message.model_dump(mode="json", by_alias=True) for message in request.messages
        ],
        "mode": request.mode,
        "request_mode": request.mode,
        "intake_index": request.intake_index,
        "intake_answers": request.intake_answers,
        "retrieved_context": [],
        "source_confidence": None,
        "citations": [],
        "escalation_trigger": request.escalation_trigger,
        "sentiment_signal": request.sentiment_signal,
        "escalation": None,
        "escalation_context": None,
        "response_text": "",
        "snapshot": None,
        "session_id": request.session_id,
        "result": None,
    }


def route_key(state: StratumState) -> ConversationMode:
    mode = state.get("mode") or "open"
    if mode not in VALID_ROUTE_KEYS:
        return "open"
    return cast(ConversationMode, mode)


def intake_branch_key(state: StratumState) -> str:
    if state.get("snapshot"):
        return "complete"
    answers = state.get("intake_answers") or {}
    index = state.get("intake_index")
    safe_index = index if index is not None else 0
    if len(answers) >= len(INTAKE_QUESTIONS) or safe_index >= len(INTAKE_QUESTIONS):
        return "complete"
    return "incomplete"


def request_from_state(state: StratumState) -> ChatRequest:
    mode = state.get("request_mode") or route_key(state)
    if mode not in VALID_ROUTE_KEYS:
        mode = "open"
    return ChatRequest.model_validate(
        {
            "messages": state["messages"],
            "mode": mode,
            "intakeIndex": state.get("intake_index"),
            "intakeAnswers": state.get("intake_answers") or {},
            "sessionId": state["session_id"],
            "escalationTrigger": state.get("escalation_trigger"),
            "sentimentSignal": state.get("sentiment_signal"),
        }
    )


def result_from_state(state: StratumState) -> StratumResult:
    result = state.get("result")
    if not result:
        raise ValueError("STRATUM graph completed without a result")
    return StratumResult.model_validate(result)


def route_node(state: StratumState) -> dict[str, Any]:
    request = request_from_state(state)
    if request.escalation_trigger:
        return {
            "mode": "escalation",
            "escalation_trigger": request.escalation_trigger,
        }
    trigger = detect_direct_trigger(last_user_text(request.messages))
    if trigger:
        return {"mode": "escalation", "escalation_trigger": trigger}
    return {"mode": route_key(state)}


def state_update_from_result(result: StratumResult) -> dict[str, Any]:
    return {
        "source_confidence": (
            result.source.model_dump(mode="json") if result.source else None
        ),
        "citations": [
            citation.model_dump(mode="json") for citation in result.citations
        ],
        "escalation_trigger": result.escalate,
        "escalation": (
            result.escalation.model_dump(mode="json") if result.escalation else None
        ),
        "response_text": result.response_text,
        "snapshot": result.snapshot.model_dump(mode="json") if result.snapshot else None,
        "result": result.model_dump(mode="json"),
    }


def _node_update_from_result(result: StratumResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, StratumResult):
        return state_update_from_result(result)
    return result


@dataclass
class StratumGraphRuntime:
    graph: Any
    database_url: str | None
    compiled: Any | None = None
    checkpointer_name: str = "uninitialized"
    _checkpointer_context: AbstractAsyncContextManager[Any] | None = None
    _init_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def respond(self, request: ChatRequest) -> StratumResult:
        compiled = await self._compiled_graph()
        final_state = await compiled.ainvoke(
            initial_state_from_request(request),
            self._config(request),
        )
        return result_from_state(cast(StratumState, final_state))

    async def stream_updates(
        self,
        request: ChatRequest,
        *,
        interrupt_after: list[str] | None = None,
    ) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        compiled = await self._compiled_graph()
        async for update in compiled.astream(
            initial_state_from_request(request),
            self._config(request),
            stream_mode="updates",
            interrupt_after=interrupt_after,
        ):
            for node_name, node_update in update.items():
                yield node_name, node_update

    async def checkpoint_result(
        self,
        request: ChatRequest,
        result: StratumResult,
        *,
        as_node: str = "generate",
    ) -> None:
        compiled = await self._compiled_graph()
        await compiled.aupdate_state(
            self._config(request),
            state_update_from_result(result),
            as_node=as_node,
        )

    async def close(self) -> None:
        context = self._checkpointer_context
        if context is None:
            return
        self._checkpointer_context = None
        self.compiled = None
        self.checkpointer_name = "uninitialized"
        await context.__aexit__(None, None, None)

    @staticmethod
    def _config(request: ChatRequest) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": request.session_id}}

    async def _compiled_graph(self) -> Any:
        if self.compiled is not None:
            return self.compiled
        async with self._init_lock:
            if self.compiled is not None:
                return self.compiled
            checkpointer, checkpointer_name, context = await _make_checkpointer(
                self.database_url
            )
            self.compiled = self.graph.compile(
                checkpointer=checkpointer,
                name="stratum",
            )
            self.checkpointer_name = checkpointer_name
            self._checkpointer_context = context
            return self.compiled


async def procedural_fallback(
    request: ChatRequest,
    *,
    open_handler: Callable[[ChatRequest], Awaitable[StratumResult]],
    intake_handler: Callable[[ChatRequest], Awaitable[StratumResult]],
    about_handler: Callable[[], StratumResult],
    escalation_handler: Callable[[ChatRequest, str], Awaitable[StratumResult]],
) -> StratumResult:
    state = initial_state_from_request(request)
    state.update(route_node(state))
    mode = route_key(state)
    if mode == "intake":
        return await intake_handler(request_from_state(state))
    if mode == "about":
        return about_handler()
    if mode == "escalation":
        trigger = state.get("escalation_trigger") or "explicit"
        return await escalation_handler(request_from_state(state), trigger)
    return await open_handler(request_from_state(state))


def build_stratum_graph(
    *,
    database_url: str | None,
    open_handler: Callable[[ChatRequest], Awaitable[StratumResult | dict[str, Any]]],
    intake_handler: Callable[[ChatRequest], Awaitable[StratumResult]],
    about_handler: Callable[[], StratumResult],
    escalation_handler: Callable[[ChatRequest, str], Awaitable[StratumResult]],
    generate_handler: Callable[[StratumState], Awaitable[StratumResult]] | None = None,
) -> StratumGraphRuntime | None:
    if StateGraph is None or MemorySaver is None:
        return None

    async def open_node(state: StratumState) -> dict[str, Any]:
        return _node_update_from_result(await open_handler(request_from_state(state)))

    async def intake_node(state: StratumState) -> dict[str, Any]:
        return state_update_from_result(await intake_handler(request_from_state(state)))

    def assess_node(state: StratumState) -> dict[str, Any]:
        return {"snapshot": state.get("snapshot")}

    def about_node(_: StratumState) -> dict[str, Any]:
        return state_update_from_result(about_handler())

    async def escalation_node(state: StratumState) -> dict[str, Any]:
        trigger = state.get("escalation_trigger") or "explicit"
        return state_update_from_result(
            await escalation_handler(request_from_state(state), trigger)
        )

    def notify_node(state: StratumState) -> dict[str, Any]:
        return {
            "escalation_context": {
                "trigger": state.get("escalation_trigger") or "explicit",
                "session_id": state["session_id"],
            }
        }

    async def generate_node(state: StratumState) -> dict[str, Any]:
        if not state.get("result") and generate_handler is not None:
            return state_update_from_result(await generate_handler(state))
        return {"response_text": state.get("response_text", "")}

    graph = StateGraph(StratumState)
    graph.add_node("route", route_node)
    graph.add_node("open", open_node)
    graph.add_node("intake", intake_node)
    graph.add_node("assess", assess_node)
    graph.add_node("about", about_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("notify", notify_node)
    graph.add_node("generate", generate_node)
    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        route_key,
        {
            "open": "open",
            "intake": "intake",
            "about": "about",
            "escalation": "escalation",
        },
    )
    graph.add_edge("open", "generate")
    graph.add_conditional_edges(
        "intake",
        intake_branch_key,
        {
            "complete": "assess",
            "incomplete": "generate",
        },
    )
    graph.add_edge("assess", "generate")
    graph.add_edge("about", "generate")
    graph.add_edge("escalation", "notify")
    graph.add_edge("notify", "generate")
    graph.add_edge("generate", END)

    return StratumGraphRuntime(
        graph=graph,
        database_url=database_url,
    )


async def _make_checkpointer(
    database_url: str | None,
) -> tuple[Any, str, AbstractAsyncContextManager[Any] | None]:
    if database_url:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            context = AsyncPostgresSaver.from_conn_string(database_url)
            checkpointer = await context.__aenter__()
            try:
                await checkpointer.setup()
                return checkpointer, "postgres", context
            except Exception:
                await context.__aexit__(None, None, None)
        except Exception:
            pass

    return MemorySaver(), "memory", None
