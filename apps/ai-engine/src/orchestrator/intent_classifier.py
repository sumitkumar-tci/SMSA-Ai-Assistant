from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    TRACKING = "TRACKING"
    # Future: RATES = "RATES", LOCATIONS = "LOCATIONS", FAQ = "FAQ"


def classify_intent(message: str) -> Intent:
    """
    Very simple keyword-based classifier for now.

    This will be replaced by a Deepseek-based classifier, but for the purposes
    of getting the tracking agent working end-to-end we keep it deterministic.
    """
    lower = message.lower()
    keywords = ("track", "awb", "shipment", "package")
    if any(k in lower for k in keywords):
        return Intent.TRACKING

    # Default to tracking so that messages still get a response in Phase 1
    return Intent.TRACKING


