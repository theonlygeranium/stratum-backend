from __future__ import annotations

import json
from typing import Any
from collections.abc import AsyncGenerator

import httpx

from app.config import Settings


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
        return None

    messages = build_chat_messages(
        system_prompt=system_prompt,
        context=context,
        conversation_history=conversation_history,
        query=query,
    )

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
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()
    except Exception:
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
        return

    messages = build_chat_messages(
        system_prompt=system_prompt,
        context=context,
        conversation_history=conversation_history,
        query=query,
    )

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
                    "max_tokens": 500,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
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
                        yield str(token)
    except Exception:
        return


def build_chat_messages(
    *,
    system_prompt: str,
    context: str,
    conversation_history: list[dict[str, str]],
    query: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Include recent conversation history so the LLM can understand
    # follow-up questions and references to prior turns.
    for msg in conversation_history[-6:]:
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
                "offer to connect the visitor with Jeffrey.\n\n"
                "--- Retrieved Context ---\n"
                f"{context}\n"
                "--- End Context ---\n\n"
                f"Visitor question: {query}"
            ),
        }
    )
    return messages
