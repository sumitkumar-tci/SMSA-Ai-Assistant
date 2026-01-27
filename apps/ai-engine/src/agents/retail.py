from __future__ import annotations

from typing import Any, Dict

from .base import BaseAgent


class RetailCentersAgent(BaseAgent):
    """
    Placeholder agent for SMSA retail / service center lookups.

    Future responsibilities:
    - Extract city/area/coordinates from context
    - Call SMSA Service Center REST API
    - Return nearest centers with address, hours, and contact details
    """

    name = "retail_centers"

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "agent": self.name,
            "content": "Retail centers agent is not implemented yet. I can only handle tracking queries for now.",
        }


