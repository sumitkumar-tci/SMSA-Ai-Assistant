from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from ..services.llm_client import SMSAAIAssistantLLMClient
from ..logging_config import logger


class Intent(str, Enum):
    TRACKING = "TRACKING"
    RATES = "RATES"
    LOCATIONS = "LOCATIONS"
    FAQ = "FAQ"
    GENERAL = "GENERAL"
    AMBIGUOUS = "AMBIGUOUS"


class SMSAAIAssistantIntentClassifier:
    """
    Intent classifier with keyword heuristics and optional LLM fallback.

    Uses keyword matching for simple queries (fast, cost-effective).
    Falls back to LLM for ambiguous or complex queries.
    """

    def __init__(self) -> None:
        self._llm_client: Optional[SMSAAIAssistantLLMClient] = None

    def _get_llm_client(self) -> SMSAAIAssistantLLMClient:
        """Lazy initialization of LLM client."""
        if self._llm_client is None:
            self._llm_client = SMSAAIAssistantLLMClient()
        return self._llm_client

    def classify(self, message: str, use_llm: bool = False) -> Intent:
        """
        Classify intent using keyword heuristics.

        Args:
            message: User message
            use_llm: If True, use LLM for classification (for ambiguous queries)

        Returns:
            Classified Intent
        """
        # Try keyword-based classification first
        lower = message.lower()

        if any(k in lower for k in ("track", "awb", "shipment", "package")):
            return Intent.TRACKING
        if any(k in lower for k in ("rate", "price", "cost", "quote")):
            return Intent.RATES
        if any(k in lower for k in ("branch", "center", "office", "location")):
            return Intent.LOCATIONS
        if any(k in lower for k in ("how do i", "what is", "faq", "question")):
            return Intent.FAQ

        # Note: For LLM-based classification, use classify_async() instead
        return Intent.GENERAL

    async def classify_async(
        self, message: str, use_llm_for_ambiguous: bool = True
    ) -> tuple[Intent, float]:
        """
        Classify intent with optional LLM fallback for ambiguous queries.

        Args:
            message: User message
            use_llm_for_ambiguous: Use LLM if keyword classification returns GENERAL

        Returns:
            Tuple of (Intent, confidence_score)
        """
        # Try keyword classification first
        intent = self.classify(message, use_llm=False)
        
        # If ambiguous and LLM is enabled, try LLM
        if intent == Intent.GENERAL and use_llm_for_ambiguous:
            try:
                llm_client = self._get_llm_client()
                result = await llm_client.classify_intent(message)
                intent_str = result.get("intent", "GENERAL")
                confidence = float(result.get("confidence", 0.5))
                
                try:
                    intent = Intent(intent_str)
                    logger.info("llm_classification_used", intent=intent_str, confidence=confidence)
                    return (intent, confidence)
                except ValueError:
                    logger.warning("invalid_intent_from_llm", intent=intent_str)
                    return (Intent.GENERAL, 0.3)
            except Exception as e:
                logger.warning("llm_classification_failed", error=str(e))
                return (Intent.GENERAL, 0.2)

        # Return keyword-based result with medium confidence
        confidence = 0.8 if intent != Intent.GENERAL else 0.3
        return (intent, confidence)

    def extract_parameters(self, message: str) -> Dict[str, Any]:
        """
        Extract lightweight parameters (e.g. AWB numbers, rate inquiry details) from the message.

        The tracking agent currently performs its own AWB extraction; this
        method exists as a central place for future expansion.
        """
        import re

        params: Dict[str, Any] = {}

        # Extract weight (e.g., "5kg", "5 kg", "weight 5", "5kg weight")
        weight_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kilograms?|kgs)?", message.lower())
        if weight_match:
            params["weight"] = weight_match.group(1)

        # Extract pieces (e.g., "1 piece", "2 pieces", "piece 1")
        pieces_match = re.search(r"(\d+)\s*(?:piece|pieces|pcs|pc)", message.lower())
        if pieces_match:
            params["pieces"] = pieces_match.group(1)

        # Common Saudi cities for rate inquiries
        saudi_cities = [
            "riyadh", "jeddah", "dammam", "khobar", "makkah", "madinah",
            "taif", "abha", "jazan", "hail", "buraidah", "tabuk",
            "najran", "al jouf", "arar", "sakaka"
        ]

        # Try to extract origin and destination cities
        lower_msg = message.lower()
        found_cities = []
        for city in saudi_cities:
            if city in lower_msg:
                found_cities.append(city.title())

        if len(found_cities) >= 2:
            params["origin_city"] = found_cities[0]
            params["destination_city"] = found_cities[1]
        elif len(found_cities) == 1:
            # If only one city found, assume it's destination (user is asking from somewhere)
            params["destination_city"] = found_cities[0]

        return params


def classify_intent(message: str) -> Intent:
    """
    Backwards-compatible helper that uses the SMSAAIAssistantIntentClassifier.
    """
    return SMSAAIAssistantIntentClassifier().classify(message)

