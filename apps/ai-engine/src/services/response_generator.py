from __future__ import annotations

from typing import Any, Dict, List


class SMSAAIAssistantResponseGenerator:
    """
    Centralized response formatter for all agents.

    Each method accepts structured data from an agent and returns a string
    suitable for streaming to the frontend.
    """

    def format_tracking(self, tracking_results: List[Dict[str, Any]]) -> str:
        """
        Format one or more tracking results into a user-facing message.

        The `tracking_results` input is expected to be a list of dicts coming
        from `TrackingResult.model_dump(by_alias=True)`.
        """
        lines: List[str] = []
        for item in tracking_results:
            awb = item.get("awb", "Unknown")
            raw = item.get("rawResponse") or {}
            friendly_status = raw.get("status") or item.get("status", "UNKNOWN")
            location = raw.get("location") or item.get("currentLocation") or "N/A"
            date = raw.get("date") or ""
            time = raw.get("time") or ""

            parts: List[str] = [
                f"AWB {awb}: {friendly_status} (location: {location})"
            ]

            if date:
                dt_part = date
                if time:
                    dt_part += f" {time}"
                parts.append(f"Last update: {dt_part}")

            history = raw.get("history") or []
            if isinstance(history, list) and history:
                preview: List[str] = []
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
                    preview.append(line)
                parts.append("Recent events:\n" + "\n".join(preview))

            lines.append("\n".join(parts))

        return "\n\n---\n\n".join(lines)

    # Stubs for future agents
    def format_rates(self, data: Dict[str, Any]) -> str:
        return "Rates agent response formatting is not implemented yet."

    def format_retail(self, data: Dict[str, Any]) -> str:
        return "Retail centers agent response formatting is not implemented yet."

    def format_faq(self, data: Dict[str, Any]) -> str:
        return "FAQ agent response formatting is not implemented yet."


