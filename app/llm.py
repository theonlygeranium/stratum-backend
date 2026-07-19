from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings


async def generate_response(
    settings: Settings,
    system_prompt: str,
    context: str,
    conversation_history: list[dict[str, str]],
    query: str,
) -> str | None:
    """Call OpenAI Chat Completions with RAG context.

    Returns the generated text or None when the API key is absent
    or the request fails. Callers must provide a fallback.
    """
    if not settings.openai_api_key:
        return None

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

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
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
