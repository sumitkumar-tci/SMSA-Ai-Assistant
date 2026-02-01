from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from .base import SMSAAIAssistantBaseAgent
from ..logging_config import logger
from ..models.tracking import TrackingResult
from ..services.smsa_apis import SMSAAIAssistantSMSATrackingClient
from ..services.llm_client import SMSAAIAssistantLLMClient

AWB_REGEX = re.compile(r"\b\d{10,15}\b")


class SMSAAIAssistantTrackingAgent(SMSAAIAssistantBaseAgent):
    """
    Agent responsible for shipment tracking queries.

    It parses AWB numbers from the user message, calls the SMSA tracking client,
    and returns a human-readable summary along with structured tracking data.
    """

    name = "tracking"

    def __init__(self) -> None:
        self._client = SMSAAIAssistantSMSATrackingClient()
        self._llm_client = SMSAAIAssistantLLMClient()

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
        
        # Extract AWBs from message
        awbs = self._extract_awbs(message)
        
        # Also check file context for extracted AWB (from Vision API)
        file_context = context.get("file_context", {})
        if file_context:
            extracted_data = file_context.get("extracted_data", {})
            if extracted_data and extracted_data.get("awb"):
                awb_from_file = extracted_data["awb"]
                if awb_from_file not in awbs:
                    awbs.append(awb_from_file)
                    logger.info("awb_extracted_from_file", awb=awb_from_file)
        
        # Also check parameters for AWB (from intent classifier or file context)
        parameters = context.get("parameters", {})
        if parameters.get("awb") and parameters["awb"] not in awbs:
            awbs.append(parameters["awb"])

        if not awbs:
            logger.info("tracking_no_awb_found", message=message)
            return {
                "agent": self.name,
                "content": "Please provide a valid AWB number to track your shipment. You can type it or upload an image of your waybill.",
                "results": [],
            }

        logger.info(
            "tracking_request",
            awbs=awbs,
            conversation_id=context.get("conversation_id"),
        )

        results: List[TrackingResult] = await self._client.track_bulk(awbs)

        logger.info(
            "tracking_response",
            awbs=[r.awb for r in results],
            count=len(results),
        )

        # Format raw data for LLM context
        tracking_data = []
        for r in results:
            raw = r.raw_response or {}
            tracking_data.append({
                "awb": r.awb,
                "status": raw.get("status") or str(r.status),
                "location": raw.get("location") or r.current_location or "N/A",
                "last_update": raw.get("date", "") + " " + raw.get("time", ""),
                "recent_events": raw.get("history", [])[:5],  # Last 5 events
            })

        # Use LLM to generate user-friendly response
        system_prompt = """You are a helpful AI assistant for SMSA Express tracking service.
Generate a friendly, clear, and informative response about shipment tracking status.
Use the tracking data provided to answer the user's question naturally and helpfully.
Be concise but include important details like current status, location, and recent events."""

        user_message = f"""User asked: {message}

Tracking data:
{json.dumps(tracking_data, indent=2)}

Generate a helpful response about the shipment status."""

        try:
            llm_response = await self._llm_client.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=500,
            )
            content = llm_response.get("content", "").strip()
            
            if not content:
                # Fallback to formatted lines
                lines: List[str] = [self._format_result_line(r) for r in results]
                content = "\n".join(lines)
        except Exception as e:
            logger.warning("llm_response_failed", error=str(e))
            # Fallback to formatted lines
            lines: List[str] = [self._format_result_line(r) for r in results]
            content = "\n".join(lines)

        return {
            "agent": self.name,
            "content": content,
            "results": [r.model_dump(by_alias=True) for r in results],
        }


