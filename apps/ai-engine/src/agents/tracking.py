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
        super().__init__()  # Load system prompt from file
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

    def _get_status_explanation(self, status: str) -> str:
        """Convert status codes to customer-friendly explanations."""
        status_lower = status.lower()
        explanations = {
            "delivered": "Your package has been successfully delivered!",
            "in_transit": "Your package is on its way to the destination.",
            "out_for_delivery": "Your package is out for delivery today!",
            "picked_up": "Your package has been picked up and is being processed.",
            "exception": "There's a delay with your shipment. Our team is working on it.",
            "pending": "Your shipment is being prepared for dispatch.",
            "returned to shipper": "Your shipment has been returned to the shipper.",
            "in_transit_to_destination": "Your package is in transit to the destination.",
        }
        # Check for partial matches
        for key, explanation in explanations.items():
            if key in status_lower:
                return explanation
        return "Your shipment is being processed."

    def _process_tracking_events(self, result: TrackingResult) -> Dict[str, Any]:
        """Process raw tracking result into structured format for frontend."""
        raw = result.raw_response or {}
        history = raw.get("history", [])
        
        # Process events chronologically (newest first in API, but we'll reverse for display)
        events = []
        for ev in reversed(history):  # Reverse to show oldest to newest
            events.append({
                "timestamp": f"{ev.get('date', '')} {ev.get('time', '')}".strip(),
                "location": ev.get("location") or ev.get("office") or "N/A",
                "description": ev.get("description") or ev.get("event_desc") or "Status update",
                "status": ev.get("status_code") or "UNKNOWN",
            })
        
        # Extract origin and destination from events
        # Origin = first event location (oldest), Destination = last event location (newest)
        origin = "N/A"
        destination = "N/A"
        
        if history:
            # History is in reverse chronological order (newest first)
            # So first item is newest (destination), last item is oldest (origin)
            if len(history) > 0:
                # Last event in history = oldest = origin
                origin_event = history[-1]
                origin = origin_event.get("location") or origin_event.get("office") or "N/A"
                
                # First event in history = newest = destination
                destination_event = history[0]
                destination = destination_event.get("location") or destination_event.get("office") or "N/A"
        
        # Fallback to raw data if available
        if origin == "N/A" and raw.get("origin"):
            origin = raw.get("origin")
        if destination == "N/A" and raw.get("destination"):
            destination = raw.get("destination")
        
        return {
            "awb": result.awb,
            "currentStatus": raw.get("status") or str(result.status),
            "statusCode": raw.get("status_code") or "",
            "location": raw.get("location") or result.current_location or "N/A",
            "lastUpdate": f"{raw.get('date', '')} {raw.get('time', '')}".strip(),
            "origin": origin,
            "destination": destination,
            "events": events,
            "serviceType": raw.get("service_type"),
            "estimatedDelivery": raw.get("estimated_delivery"),
        }

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

        # If no AWB found, let LLM handle conversationally (greetings, off-topic, etc.)
        if not awbs:
            logger.info("tracking_no_awb_found", message=message)
            
            # Use LLM for all conversational queries (no instant responses)
            system_prompt = self.system_prompt or """You are a friendly SMSA Express tracking assistant. 
            Help customers track shipments. If they greet you, respond warmly and ask for AWB number.
            If they ask off-topic questions, politely redirect to tracking. Always be helpful and professional.
            Keep responses concise and natural (2-3 sentences max)."""
            
            try:
                # Let LLM handle the conversation
                llm_response = await self._llm_client.chat_completion(
                    messages=[{"role": "user", "content": message}],
                    system_prompt=system_prompt,
                    temperature=0.7,
                    max_tokens=200,  # Allow natural conversational responses
                )
                content = llm_response.get("content", "").strip()
                
                if not content:
                    content = "I'd be happy to help you track your shipment! Please provide your AWB (tracking) number, and I'll get the latest status for you."
            except Exception as e:
                logger.warning("llm_conversational_response_failed", error=str(e))
                content = "I'd be happy to help you track your shipment! Please provide your AWB (tracking) number, and I'll get the latest status for you."
            
            return {
                "agent": self.name,
                "content": content,
                "results": [],
                "type": "conversational",
                "requires_awb": True,
            }

        logger.info(
            "tracking_request",
            awbs=awbs,
            conversation_id=context.get("conversation_id"),
        )

        # Call SMSA tracking API
        try:
            results: List[TrackingResult] = await self._client.track_bulk(awbs)

            logger.info(
                "tracking_response",
                awbs=[r.awb for r in results],
                count=len(results),
            )
        except Exception as e:
            logger.error("tracking_api_error", error=str(e), awbs=awbs)
            # Handle API errors gracefully with LLM
            system_prompt = self.system_prompt or ""
            error_message = f"I encountered an issue while tracking AWB {awbs[0] if awbs else 'your shipment'}. Please try again in a moment, or contact SMSA Express customer support for assistance."
            
            try:
                llm_response = await self._llm_client.chat_completion(
                    messages=[{"role": "user", "content": f"User asked: {message}\n\nError occurred: {str(e)}"}],
                    system_prompt=system_prompt,
                    temperature=0.7,
                    max_tokens=150,
                )
                error_message = llm_response.get("content", "").strip() or error_message
            except Exception:
                pass  # Use default error message
            
            return {
                "agent": self.name,
                "content": error_message,
                "results": [],
                "type": "error",
            }

        # Process tracking data into structured format
        processed_data_list = []
        for r in results:
            processed_data = self._process_tracking_events(r)
            processed_data_list.append(processed_data)

        # Format data for LLM context
        tracking_data = []
        for processed in processed_data_list:
            tracking_data.append({
                "awb": processed["awb"],
                "status": processed["currentStatus"],
                "location": processed["location"],
                "last_update": processed["lastUpdate"],
                "origin": processed["origin"],
                "destination": processed["destination"],
                "events": processed["events"],
                "status_explanation": self._get_status_explanation(processed["currentStatus"]),
            })

        # Use LLM to generate user-friendly conversational response
        system_prompt = self.system_prompt or """You are a friendly SMSA Express tracking assistant."""
        
        user_message = f"""User asked: {message}

Tracking data:
{json.dumps(tracking_data, indent=2)}

Generate a helpful, conversational response about the shipment status. Start with current status, explain what it means, then show the shipment journey with all events."""

        try:
            llm_response = await self._llm_client.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=400,  # Reduced from 600 for faster responses (structured data handles details)
            )
            content = llm_response.get("content", "").strip()
            
            # Additional cleanup: remove any remaining reasoning content (defense in depth)
            # The LLM client already cleans, but we do it again here as a safety measure
            # This ensures no reasoning leaks through
            if content:
                # Remove sentences that start with reasoning patterns
                import re
                lines = content.split('\n')
                cleaned_lines = []
                for line in lines:
                    line_lower = line.lower().strip()
                    # Skip lines that are clearly reasoning
                    reasoning_starters = [
                        'okay', 'i need to', 'let me', 'first', 'i should', 'maybe',
                        'also', 'the rules', 'the example', 'let me check', 'let me see',
                        'since', 'i should make sure', 'let me structure', 'wts is this'
                    ]
                    if not any(line_lower.startswith(starter) for starter in reasoning_starters):
                        cleaned_lines.append(line)
                content = '\n'.join(cleaned_lines).strip()
                
                # Also remove tagged reasoning
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'<reasoning>.*?</reasoning>', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = content.strip()
            
            if not content:
                # Fallback to formatted lines
                lines: List[str] = [self._format_result_line(r) for r in results]
                content = "\n".join(lines)
        except Exception as e:
            logger.warning("llm_response_failed", error=str(e))
            # Fallback to formatted lines
            lines: List[str] = [self._format_result_line(r) for r in results]
            content = "\n".join(lines)

        # Return both LLM response and structured data for frontend
        return {
            "agent": self.name,
            "content": content,
            "results": [r.model_dump(by_alias=True) for r in results],
            "type": "tracking_result",
            "raw_data": processed_data_list[0] if processed_data_list else {},  # Structured data for frontend
            "events": processed_data_list[0].get("events", []) if processed_data_list else [],
            "current_status": processed_data_list[0].get("currentStatus", "") if processed_data_list else "",
            "status_explanation": self._get_status_explanation(processed_data_list[0].get("currentStatus", "")) if processed_data_list else "",
        }


