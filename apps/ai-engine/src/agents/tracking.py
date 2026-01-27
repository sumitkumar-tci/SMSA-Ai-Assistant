from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import BaseAgent
from ..logging_config import logger
from ..models.tracking import TrackingResult
from ..services.smsa_apis import SMSATrackingClient

AWB_REGEX = re.compile(r"\b\d{10,15}\b")


class TrackingAgent(BaseAgent):
    """
    Agent responsible for shipment tracking queries.

    It parses AWB numbers from the user message, calls the SMSA tracking client,
    and returns a human-readable summary along with structured tracking data.
    """

    name = "tracking"

    def __init__(self) -> None:
        self._client = SMSATrackingClient()

    def _extract_awbs(self, text: str) -> List[str]:
        """Extract unique AWB-like numbers from the input text."""
        return list({match.group(0) for match in AWB_REGEX.finditer(text)})

    def _format_result_line(self, result: TrackingResult) -> str:
        """
        Build a rich, user-facing line for a single AWB using the
        structured data from SMSA if available.
        """
        raw = result.raw_response or {}
        # Friendly status text from parser (e.g. "Returned to Shipper")
        friendly_status = raw.get("status") or result.status
        location = raw.get("location") or result.current_location or "N/A"
        date = raw.get("date") or ""
        time = raw.get("time") or ""

        parts: List[str] = [f"AWB {result.awb}: {friendly_status} (location: {location})"]

        if date:
            dt_part = date
            if time:
                dt_part += f" {time}"
            parts.append(f"Last update: {dt_part}")

        # Optionally include a short history summary (most recent few events)
        history = raw.get("history") or []
        if isinstance(history, list) and history:
            events_preview = []
            for ev in history[:3]:
                desc = ev.get("description") or "Status update"
                loc = ev.get("location") or "N/A"
                ev_date = ev.get("date") or ""
                ev_time = ev.get("time") or ""
                line = f"- {desc} @ {loc}"
                if ev_date:
                    line += f" ({ev_date}"
                    if ev_time:
                        line += f" {ev_time}"
                    line += ")"
                events_preview.append(line)
            parts.append("Recent events:\n" + "\n".join(events_preview))

        return "\n".join(parts)

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        message: str = context["message"]
        awbs = self._extract_awbs(message)

        if not awbs:
            logger.info("tracking_no_awb_found", message=message)
            return {
                "agent": self.name,
                "content": "Please provide a valid AWB number to track your shipment.",
                "results": [],
            }

        logger.info(
            "tracking_request",
            awbs=awbs,
            conversation_id=context.get("conversation_id"),
        )

        results: List[TrackingResult] = await self._client.track_bulk(awbs)

        lines: List[str] = [self._format_result_line(r) for r in results]

        logger.info(
            "tracking_response",
            awbs=[r.awb for r in results],
            count=len(results),
        )

        return {
            "agent": self.name,
            "content": "\n".join(lines),
            "results": [r.model_dump(by_alias=True) for r in results],
        }


