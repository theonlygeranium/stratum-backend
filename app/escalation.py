from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.models import ChatMessage, ChatRequest, ReadinessSnapshot


EXPLICIT_KEYWORDS = [
    "jeffrey",
    "founder",
    "human",
    "real person",
    "talk to jeffrey",
    "connect me with the founder",
    "i want to start a project",
    "speak to jeffrey",
    "connect me with jeffrey",
]

FRUSTRATION_KEYWORDS = [
    "this isn't helping",
    "this is not helping",
    "not helpful",
    "you don't understand",
    "i already told you",
    "forget it",
    "this is useless",
    "can i talk to a human",
]


def last_user_text(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def detect_direct_trigger(text: str) -> str | None:
    lowered = text.lower()
    if any(keyword in lowered for keyword in EXPLICIT_KEYWORDS):
        return "explicit"
    if any(keyword in lowered for keyword in FRUSTRATION_KEYWORDS):
        return "sentiment"
    return None


def detect_high_intent(request: ChatRequest) -> bool:
    joined_answers = " ".join(str(value).lower() for value in request.intake_answers.values())
    joined_messages = " ".join(message.content.lower() for message in request.messages)
    return any(
        signal in f"{joined_answers} {joined_messages}"
        for signal in [
            "30-60 days",
            "30–60 days",
            "30 to 60 days",
            "3-6 months",
            "3–6 months",
            "budget allocated",
            "engineering team ready",
            "ready to start",
        ]
    )


def extract_contact(messages: list[ChatMessage]) -> dict[str, str | None]:
    transcript = "\n".join(message.content for message in messages)
    email = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", transcript)
    phone = re.search(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", transcript)
    return {
        "email": email.group(0) if email else None,
        "phone": phone.group(0) if phone else None,
    }


def format_transcript(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{message.role.upper()}: {message.content}" for message in messages)


def build_payload(
    request: ChatRequest,
    trigger: str,
    snapshot: ReadinessSnapshot | None,
) -> dict[str, Any]:
    return {
        "conversation_transcript": format_transcript(request.messages),
        "readiness_snapshot": snapshot.model_dump() if snapshot else None,
        "intent_category": request.mode,
        "key_signals": {
            "organization_type": request.intake_answers.get("org-type"),
            "canvas_usage": request.intake_answers.get("canvas-usage"),
            "timeline": request.intake_answers.get("timeline"),
            "problem": request.intake_answers.get("problem"),
        },
        "escalation_trigger": trigger,
        "visitor_contact": extract_contact(request.messages),
        "session_id": request.session_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def format_email_html(payload: dict[str, Any]) -> str:
    snapshot = payload.get("readiness_snapshot") or {}
    return f"""
    <h1>STRATUM Escalation - {html.escape(payload['escalation_trigger'])}</h1>
    <p><strong>Session:</strong> {html.escape(payload['session_id'])}</p>
    <p><strong>Timestamp:</strong> {html.escape(payload['timestamp'])}</p>
    <h2>Readiness Snapshot</h2>
    <p><strong>Your Situation:</strong> {html.escape(snapshot.get('situation', 'Not completed'))}</p>
    <p><strong>Relevant Capabilities:</strong> {html.escape(snapshot.get('capabilities', 'Not completed'))}</p>
    <p><strong>Realistic First Step:</strong> {html.escape(snapshot.get('firstStep', 'Not completed'))}</p>
    <h2>Key Signals</h2>
    <pre>{html.escape(json.dumps(payload.get('key_signals', {}), indent=2))}</pre>
    <h2>Visitor Contact</h2>
    <pre>{html.escape(json.dumps(payload.get('visitor_contact', {}), indent=2))}</pre>
    <h2>Transcript</h2>
    <pre>{html.escape(payload.get('conversation_transcript', ''))}</pre>
    """


async def send_or_log_escalation(
    settings: Settings,
    payload: dict[str, Any],
) -> bool:
    settings.escalation_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(settings.escalation_log_dir) / f"{payload['session_id']}.json"
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not settings.resend_api_key or not settings.jeffrey_email:
        return False

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": "stratum@edstratumlabs.ai",
                "to": [settings.jeffrey_email],
                "subject": f"STRATUM Escalation - {payload['escalation_trigger'].title()} Trigger",
                "html": format_email_html(payload),
            },
        )
        response.raise_for_status()
    return True
