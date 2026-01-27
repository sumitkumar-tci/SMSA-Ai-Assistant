from __future__ import annotations

from typing import Any, Dict

from .base import BaseAgent


class RatesAgent(BaseAgent):
    """
    Placeholder agent for shipping rate inquiries.

    Future responsibilities:
    - Extract origin/destination/weight/dimensions from context
    - Call SMSA Rates REST API
    - Format rate options for the response generator
    """

    name = "rates"

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "agent": self.name,
            "content": "Rates agent is not implemented yet. I can only handle tracking queries for now.",
        }


