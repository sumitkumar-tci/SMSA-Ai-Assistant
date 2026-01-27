from __future__ import annotations

from typing import Any, Dict

from .intent_classifier import Intent, classify_intent
from ..agents.tracking import TrackingAgent


tracking_agent = TrackingAgent()


async def route_message(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route the incoming message to the appropriate agent based on intent.

    For Phase 1 we only support the TRACKING intent, which is handled by
    `TrackingAgent`.
    """
    message: str = context["message"]
    explicit_intent = context.get("explicit_intent")

    if isinstance(explicit_intent, Intent):
        intent = explicit_intent
    elif isinstance(explicit_intent, str):
        try:
            intent = Intent(explicit_intent)
        except ValueError:
            intent = classify_intent(message)
    else:
        intent = classify_intent(message)

    context["intent"] = intent

    if intent == Intent.TRACKING:
        return await tracking_agent.run(context)

    # Fallback – should not be hit in Phase 1
    return {
        "agent": "system",
        "content": "This type of request is not yet supported.",
    }


