from __future__ import annotations

from typing import Any, Dict, List


class SMSAAIAssistantDeepseekIntentClient:
    """
    Placeholder client for Deepseek-based intent classification.

    In Phase 2 this will:
    - Call Deepseek chat/embeddings API with a prompt and conversation context
    - Return a structured intent label and extracted entities/parameters
    """

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    async def classify_intent(
        self, message: str, conversation_history: List[Dict[str, Any]] | None = None
    ) -> Dict[str, Any]:
        """
        Analyze a user message and return an intent + optional parameters.

        For now this is a stub that always returns TRACKING; the keyword-based
        classifier remains the source of truth until Deepseek is wired in.
        """
        return {
            "intent": "TRACKING",
            "confidence": 0.0,
            "parameters": {},
            "provider": "deepseek_stub",
        }


