from __future__ import annotations

import json
from typing import Any
from collections.abc import AsyncGenerator

import httpx

from app.config import Settings
from app.observability import LatencyTimer, increment_counter, log_event


async def generate_response(
    settings: Settings,
    system_prompt: str,
    context: str,
    conversation_history: list[dict[str, str]],
    query: str,
) -> str | None:
    """Call an OpenAI-compatible Chat Completions endpoint with RAG context.

    Works with any provider that matches the OpenAI response format
    (choices[0].message.content), including OpenAI itself and WRITER
    Palmyra (api.writer.com/v1/chat). The endpoint, key, and model
    are all configurable via Settings / environment variables.

    Returns the generated text or None when the API key is absent
    or the request fails. Callers must provide a fallback.
    """
    if not settings.llm_api_key:
        log_event(
            "warning",
            "llm_skipped",
            reason="no_api_key",
            provider=settings.llm_provider,
        )
        return None

    messages = await build_chat_messages(
        settings=settings,
        system_prompt=system_prompt,
        context=context,
        conversation_history=conversation_history,
        query=query,
    )

    with LatencyTimer(
        "llm_generate_latency",
        provider=settings.llm_provider,
        model=settings.llm_model,
    ):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    settings.llm_base_url,
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.llm_model,
                        "messages": messages,
                        "temperature": 0.3,
                        "max_tokens": settings.llm_max_tokens,
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                increment_counter("llm_generate_success")
                return str(data["choices"][0]["message"]["content"]).strip()
        except Exception as exc:
            increment_counter("llm_generate_failure")
            log_event(
                "error",
                "llm_generate_error",
                provider=settings.llm_provider,
                error_type=type(exc).__name__,
                error_message=str(exc)[:200],
            )
        return None


async def stream_response(
    settings: Settings,
    system_prompt: str,
    context: str,
    conversation_history: list[dict[str, str]],
    query: str,
) -> AsyncGenerator[str, None]:
    """Stream token deltas from an OpenAI-compatible Chat Completions endpoint."""
    if not settings.llm_api_key:
        log_event(
            "warning",
            "llm_stream_skipped",
            reason="no_api_key",
            provider=settings.llm_provider,
        )
        return

    messages = await build_chat_messages(
        settings=settings,
        system_prompt=system_prompt,
        context=context,
        conversation_history=conversation_history,
        query=query,
    )

    with LatencyTimer(
        "llm_stream_latency",
        provider=settings.llm_provider,
        model=settings.llm_model,
    ):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream(
                    "POST",
                    settings.llm_base_url,
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.llm_model,
                        "messages": messages,
                        "temperature": 0.3,
                        "max_tokens": settings.llm_max_tokens,
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()
                    saw_token = False
                    async for line in response.aiter_lines():
                        payload = line.strip()
                        if not payload.startswith("data:"):
                            continue
                        payload = payload.removeprefix("data:").strip()
                        if payload == "[DONE]":
                            break
                        try:
                            data: dict[str, Any] = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choice = (data.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        token = delta.get("content")
                        if token:
                            saw_token = True
                            yield str(token)
                    if saw_token:
                        increment_counter("llm_stream_success")
        except Exception as exc:
            increment_counter("llm_stream_failure")
            log_event(
                "error",
                "llm_stream_error",
                provider=settings.llm_provider,
                error_type=type(exc).__name__,
                error_message=str(exc)[:200],
            )
        return


async def build_chat_messages(
    *,
    settings: Settings,
    system_prompt: str,
    context: str,
    conversation_history: list[dict[str, str]],
    query: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    recent_window = max(0, settings.llm_history_window)
    summary_threshold = max(recent_window, settings.llm_summary_threshold)
    history = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in conversation_history
        if msg.get("role") in {"user", "assistant"} and msg.get("content")
    ]

    if len(history) > summary_threshold and recent_window:
        summary = await _summarize_history(settings, history[:-recent_window])
        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Conversation summary so far: {summary}",
                }
            )

    # Include recent conversation history so the LLM can understand
    # follow-up questions and references to prior turns.
    for msg in history[-recent_window:] if recent_window else []:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Present the retrieved context and the visitor's question together
    # so the model grounds its answer in the knowledge base.
    messages.append(
        {
            "role": "user",
            "content": (
                "Use the following context from the EdStratum knowledge base "
                "to answer the visitor's question. If the context does not "
                "contain enough information to answer confidently, say so and "
                "offer to connect the visitor with EdStratum's Founding leadership team.\n\n"
                "--- Retrieved Context ---\n"
                f"{context}\n"
                "--- End Context ---\n\n"
                f"Visitor question: {query}"
            ),
        }
    )
    return messages


async def _summarize_history(
    settings: Settings,
    history: list[dict[str, str]],
) -> str | None:
    if not history:
        return None

    transcript = "\n".join(
        f"{message['role']}: {message['content'][:800]}" for message in history
    )
    messages = [
        {
            "role": "system",
            "content": (
                "Summarize the older STRATUM conversation context in under 120 words. "
                "Preserve the visitor's business problem, constraints, readiness signals, "
                "and unresolved asks. Do not invent facts."
            ),
        },
        {
            "role": "user",
            "content": transcript,
        },
    ]

    with LatencyTimer(
        "llm_summary_latency",
        provider=settings.llm_provider,
        model=settings.llm_model,
    ):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    settings.llm_base_url,
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.llm_model,
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": max(64, min(160, settings.llm_max_tokens)),
                    },
                )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                summary = str(data["choices"][0]["message"]["content"]).strip()
                if summary:
                    increment_counter("llm_summary_success")
                    return summary
        except Exception as exc:
            increment_counter("llm_summary_failure")
            log_event(
                "warning",
                "llm_summary_error",
                provider=settings.llm_provider,
                error_type=type(exc).__name__,
                error_message=str(exc)[:200],
            )
    return None
