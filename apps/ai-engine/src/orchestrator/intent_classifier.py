from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class Intent(str, Enum):
    TRACKING = "TRACKING"
    RATES = "RATES"
    LOCATIONS = "LOCATIONS"
    FAQ = "FAQ"
    GENERAL = "GENERAL"
    AMBIGUOUS = "AMBIGUOUS"


class IntentClassifier:
    """
    Lightweight intent classifier used by the AI orchestrator.

    Phase 1: simple keyword heuristics.
    Phase 2: delegate to DeepseekIntentClient for semantic classification.
    """

    def classify(self, message: str) -> Intent:
        lower = message.lower()

        if any(k in lower for k in ("track", "awb", "shipment", "package")):
            return Intent.TRACKING
        if any(k in lower for k in ("rate", "price", "cost", "quote")):
            return Intent.RATES
        if any(k in lower for k in ("branch", "center", "office", "location")):
            return Intent.LOCATIONS
        if any(k in lower for k in ("how do i", "what is", "faq", "question")):
            return Intent.FAQ

        return Intent.GENERAL

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
    Backwards-compatible helper that uses the IntentClassifier.
    """
    return IntentClassifier().classify(message)

