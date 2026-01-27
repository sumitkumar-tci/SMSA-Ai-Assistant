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
        Extract lightweight parameters (e.g. AWB numbers) from the message.

        The tracking agent currently performs its own AWB extraction; this
        method exists as a central place for future expansion.
        """
        return {}


def classify_intent(message: str) -> Intent:
    """
    Backwards-compatible helper that uses the IntentClassifier.
    """
    return IntentClassifier().classify(message)

