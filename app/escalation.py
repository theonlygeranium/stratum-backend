from __future__ import annotations

import html
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.models import ChatMessage, ChatRequest, EscalationDelivery, ReadinessSnapshot


RESEND_FALLBACK_FROM_EMAIL = "onboarding@resend.dev"
RATE_LIMIT_MAX_EMAILS = 3
RATE_LIMIT_WINDOW_SECONDS = 60 * 60
_ESCALATION_SENDS: dict[str, list[float]] = {}

EXPLICIT_KEYWORDS = [
    "talk to jeffrey",
    "talk to the founding leadership team",
    "talk to founding leadership",
    "talk to leadership",
    "speak to the founding leadership team",
    "speak to founding leadership",
    "speak to leadership",
    "connect me with the founding leadership team",
    "connect me with founding leadership",
    "connect me with leadership",
    "connect me to the founding leadership team",
    "connect me to founding leadership",
    "connect me to leadership",
    "connect me with the founder's leadership team",
    "connect me to the founder's leadership team",
    "talk to the founder's leadership team",
    "speak to the founder's leadership team",
    "connect me with the founder",
    "i want to start a project",
    "speak to jeffrey",
    "connect me with jeffrey",
    "connect with jeffrey",
    "talk to a real person",
    "speak to a real person",
    "connect me with a real person",
    "connect me to a real person",
    "get in touch",
    "schedule a call",
    "schedule a meeting",
    "book a call",
    "book a meeting",
    "set up a call",
    "set up a meeting",
    "can someone contact",
    "reach out to me",
    "reach out to you",
    "how do i contact",
    "how do i reach",
    "talk to someone",
    "speak to someone",
    "speak with someone",
    "connect me",
    "connect with someone",
    "i want to talk",
    "i'd like to talk",
    "i would like to talk",
    "can we talk",
    "can we speak",
    "let's chat",
    "free consultation",
    "discovery call",
    "initial call",
    "hire you",
    "hire edstratum",
    "work with you",
    "work with edstratum",
    "engage edstratum",
    "how much",
    "what does it cost",
    "how much does this cost",
    "pricing for this",
    "pricing for an engagement",
    "quote",
    "get a quote",
]

FRUSTRATION_KEYWORDS = [
    "this isn't helping",
    "this is not helping",
    "not helpful",
    "you don't understand",
    "you do not understand",
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
    if any(_contains_keyword(lowered, keyword) for keyword in FRUSTRATION_KEYWORDS):
        return "sentiment"
    if any(_contains_keyword(lowered, keyword) for keyword in EXPLICIT_KEYWORDS):
        return "explicit"
    return None


def _contains_keyword(text: str, keyword: str) -> bool:
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text) is not None


def detect_high_intent(request: ChatRequest) -> bool:
    joined_answers = " ".join(str(value).lower() for value in request.intake_answers.values())
    joined_messages = " ".join(message.content.lower() for message in request.messages)
    return any(
        signal in f"{joined_answers} {joined_messages}"
        for signal in [
            "30-60 days",
            "30\u201360 days",
            "30 to 60 days",
            "3-6 months",
            "3\u20136 months",
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
    key_signals: dict[str, str | None] = {
        "organization_type": request.intake_answers.get("org-type"),
        "canvas_usage": request.intake_answers.get("canvas-usage"),
        "timeline": request.intake_answers.get("timeline"),
        "problem": request.intake_answers.get("problem"),
    }
    if request.sentiment_signal:
        key_signals["sentiment_signal"] = request.sentiment_signal

    return {
        "conversation_transcript": format_transcript(request.messages),
        "readiness_snapshot": snapshot.model_dump() if snapshot else None,
        "intent_category": request.mode,
        "key_signals": key_signals,
        "escalation_trigger": trigger,
        "visitor_contact": extract_contact(request.messages),
        "session_id": request.session_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def format_email_html(payload: dict[str, Any]) -> str:
    snapshot = payload.get("readiness_snapshot") or {}
    return f"""
    <div style="font-family:Inter,Arial,sans-serif;color:#111827;background:#ffffff">
      <div style="background:#111827;color:#ffffff;padding:20px;border-radius:8px 8px 0 0">
        <h1 style="margin:0;font-size:20px">EdStratum Labs STRATUM Handoff</h1>
        <p style="margin:8px 0 0;color:#c4b5fd">Trigger: {html.escape(payload['escalation_trigger'])}</p>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:0;padding:20px;border-radius:0 0 8px 8px">
        <p><strong>Session ID:</strong> {html.escape(payload['session_id'])}</p>
        <p><strong>Timestamp:</strong> {html.escape(payload['timestamp'])}</p>
        <h2 style="color:#7c3aed">Lead Info</h2>
        <pre>{html.escape(json.dumps(payload.get('visitor_contact', {}), indent=2))}</pre>
        <h2 style="color:#7c3aed">Intake Summary</h2>
        <table cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
          <tr><td><strong>Your Situation</strong></td><td>{html.escape(snapshot.get('situation', 'Not completed'))}</td></tr>
          <tr><td><strong>Relevant Capabilities</strong></td><td>{html.escape(snapshot.get('capabilities', 'Not completed'))}</td></tr>
          <tr><td><strong>Realistic First Step</strong></td><td>{html.escape(snapshot.get('firstStep', 'Not completed'))}</td></tr>
        </table>
        <h2 style="color:#7c3aed">Escalation Reason</h2>
        <p>{html.escape(payload['escalation_trigger'])}</p>
        <h2 style="color:#7c3aed">Key Signals</h2>
        <pre>{html.escape(json.dumps(payload.get('key_signals', {}), indent=2))}</pre>
        <h2 style="color:#7c3aed">Transcript</h2>
        <pre>{html.escape(payload.get('conversation_transcript', ''))}</pre>
      </div>
    </div>
    """


def format_email_text(payload: dict[str, Any]) -> str:
    snapshot = payload.get("readiness_snapshot") or {}
    return "\n\n".join(
        [
            "EdStratum Labs STRATUM Handoff",
            f"Session ID: {payload['session_id']}",
            f"Timestamp: {payload['timestamp']}",
            f"Escalation Reason: {payload['escalation_trigger']}",
            "Lead Info:\n" + json.dumps(payload.get("visitor_contact", {}), indent=2),
            "Intake Summary:\n"
            f"Your Situation: {snapshot.get('situation', 'Not completed')}\n"
            f"Relevant Capabilities: {snapshot.get('capabilities', 'Not completed')}\n"
            f"Realistic First Step: {snapshot.get('firstStep', 'Not completed')}",
            "Key Signals:\n" + json.dumps(payload.get("key_signals", {}), indent=2),
            "Transcript:\n" + payload.get("conversation_transcript", ""),
        ]
    )


def _consume_rate_limit(session_id: str) -> bool:
    now = time.time()
    recent = [
        timestamp
        for timestamp in _ESCALATION_SENDS.get(session_id, [])
        if now - timestamp < RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(recent) >= RATE_LIMIT_MAX_EMAILS:
        _ESCALATION_SENDS[session_id] = recent
        return False
    recent.append(now)
    _ESCALATION_SENDS[session_id] = recent
    return True


async def send_or_log_escalation(
    settings: Settings,
    payload: dict[str, Any],
    *,
    suppress_notifications: bool = False,
) -> EscalationDelivery:
    settings.escalation_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(settings.escalation_log_dir) / f"{payload['session_id']}.json"
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if suppress_notifications:
        return EscalationDelivery(
            success=True,
            status="suppressed",
            messageId="qa-suppressed",
        )

    if not settings.resend_api_key or not settings.jeffrey_email:
        return EscalationDelivery(
            success=False,
            status="prepared",
            error="notifications_not_configured",
        )

    if not _consume_rate_limit(str(payload["session_id"])):
        payload["suppressed_reason"] = "rate_limited"
        log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return EscalationDelivery(
            success=False,
            status="rate_limited",
            error="rate_limited",
        )

    senders = list(
        dict.fromkeys([settings.resend_from_email, RESEND_FALLBACK_FROM_EMAIL])
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for sender in senders:
                try:
                    response = await client.post(
                        "https://api.resend.com/emails",
                        headers={
                            "Authorization": f"Bearer {settings.resend_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "from": sender,
                            "to": [settings.jeffrey_email],
                            "subject": (
                                "[EdStratum Labs] New Qualified Lead - "
                                f"{payload['timestamp']}"
                            ),
                            "html": format_email_html(payload),
                            "text": format_email_text(payload),
                        },
                    )
                    response.raise_for_status()
                    message_id = "resend-accepted"
                    try:
                        data = response.json()
                        if isinstance(data, dict) and data.get("id"):
                            message_id = str(data["id"])
                    except Exception:
                        pass
                    return EscalationDelivery(
                        success=True,
                        status="sent",
                        messageId=message_id,
                    )
                except Exception:
                    continue
    except Exception:
        pass

    # Email notification failed, but the escalation was already logged
    # to disk above. Do not crash the user-facing response.
    return EscalationDelivery(
        success=False,
        status="failed",
        error="resend_delivery_failed",
    )
