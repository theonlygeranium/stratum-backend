CORE_PERSONA = """You are STRATUM, EdStratum Labs' AI Strategy Intake and Discovery Advisor.
You are an AI intake advisor, not a human. You are transparent from the first message.
You work directly with Jeffrey and answer in an evidence-driven, anti-hype voice.
Never hallucinate. If context is absent, say so and offer escalation to Jeffrey.
"""

SCOPE_BOUNDARY_MESSAGE = (
    "I'm scoped specifically to EdStratum's services and AI implementation context. "
    "For that topic, I'd recommend checking general resources - or I can connect you "
    "with Jeffrey for a broader conversation."
)

CONFIDENCE_ESCALATION_MESSAGE = (
    "That's getting into territory I'd rather have Jeffrey address directly - "
    "he'll give you a more accurate answer than I can."
)

HIGH_INTENT_ESCALATION_MESSAGE = (
    "Based on what you've described, this sounds like it could be a strong fit for "
    "EdStratum. Want me to connect you with Jeffrey directly?"
)

ESCALATION_SLA_MESSAGE = (
    "I've sent Jeffrey a summary of our conversation. He typically responds within "
    "one business day."
)

INTAKE_QUESTIONS = [
    {
        "id": "org-type",
        "text": "What type of organization are you?",
        "options": ["EdTech platform", "Higher Ed institution", "K-12", "Other"],
    },
    {
        "id": "canvas-usage",
        "text": "Are you currently using Instructure Canvas? If so, in what capacity?",
        "options": [],
    },
    {
        "id": "problem",
        "text": "What problem are you trying to solve with AI?",
        "options": [],
    },
    {
        "id": "data-infra",
        "text": "What is your current data infrastructure and quality level?",
        "options": ["Mature / clean", "Developing", "Minimal / messy", "Unknown"],
    },
    {
        "id": "engineering",
        "text": "Do you have an internal engineering team, or would this be fully outsourced?",
        "options": ["Internal team", "Fully outsourced", "Hybrid", "Not sure yet"],
    },
    {
        "id": "timeline",
        "text": "What is your approximate timeline for an AI initiative?",
        "options": ["30-60 days", "3-6 months", "6-12 months", "Exploring"],
        "high_intent": True,
    },
    {
        "id": "success",
        "text": "What does success look like in 6 months?",
        "options": [],
    },
]
