from __future__ import annotations

from typing import Any, Dict

from .intent_classifier import Intent, IntentClassifier
from ..agents.tracking import TrackingAgent
from ..agents.rates import RatesAgent
from ..agents.retail import RetailCentersAgent
from ..agents.faq import FAQAgent


class AIOrchestrator:
    """
    High-level orchestrator responsible for:
    - Intent classification
    - Context assembly (conversation, files, memory)
    - Routing to specialized agents
    - Aggregating responses
    """

    def __init__(self) -> None:
        self._classifier = IntentClassifier()
        self._tracking_agent = TrackingAgent()
        self._rates_agent = RatesAgent()
        self._retail_agent = RetailCentersAgent()
        self._faq_agent = FAQAgent()

    async def handle(self, context: Dict[str, Any]) -> Dict[str, Any]:
        message: str = context["message"]
        explicit_intent = context.get("explicit_intent")

        if isinstance(explicit_intent, Intent):
            intent = explicit_intent
        elif isinstance(explicit_intent, str):
            try:
                intent = Intent(explicit_intent)
            except ValueError:
                intent = self._classifier.classify(message)
        else:
            intent = self._classifier.classify(message)

        context["intent"] = intent
        parameters = self._classifier.extract_parameters(message)
        context.setdefault("parameters", {}).update(parameters)

        if intent == Intent.TRACKING:
            return await self._tracking_agent.run(context)
        if intent == Intent.RATES:
            return await self._rates_agent.run(context)
        if intent == Intent.LOCATIONS:
            return await self._retail_agent.run(context)
        if intent == Intent.FAQ:
            return await self._faq_agent.run(context)

        # GENERAL / AMBIGUOUS – for now return a friendly fallback
        return {
            "agent": "system",
            "content": "I can help with tracking, rates, service centers, and FAQs. Please specify what you need.",
        }


_orchestrator = AIOrchestrator()


async def route_message(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy entrypoint used by the FastAPI route.

    Delegates to the `AIOrchestrator` instance to keep the public interface
    stable while we expand the orchestration layer.
    """
    return await _orchestrator.handle(context)

