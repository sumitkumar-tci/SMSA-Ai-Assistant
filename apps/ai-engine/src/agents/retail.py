from __future__ import annotations

from typing import Any, Dict, List

from ..logging_config import logger
from ..services.smsa_apis import SMSAAIAssistantSMSARetailCentersClient
from ..services.llm_client import SMSAAIAssistantLLMClient
from .base import SMSAAIAssistantBaseAgent


class SMSAAIAssistantRetailCentersAgent(SMSAAIAssistantBaseAgent):
    """
    Agent for finding SMSA retail/service centers.

    Extracts city/location from user message and calls SMSA Retail Centers API
    to return nearest service centers with addresses, hours, and contact info.
    """

    name = "retail_centers"

    # Common Saudi cities
    SAUDI_CITIES = [
        "riyadh", "jeddah", "dammam", "khobar", "makkah", "madinah",
        "taif", "abha", "jazan", "hail", "buraidah", "tabuk",
        "najran", "al jouf", "arar", "sakaka", "qassim", "yanbu",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._client = SMSAAIAssistantSMSARetailCentersClient()
        self._llm_client = SMSAAIAssistantLLMClient()

    def _extract_city(self, message: str) -> str | None:
        """Extract city name from user message."""
        lower_msg = message.lower()
        for city in self.SAUDI_CITIES:
            if city in lower_msg:
                return city.title()
        return None

    def _format_centers(self, centers: List[Dict[str, Any]]) -> str:
        """Format centers list into user-friendly text."""
        if not centers:
            return "No service centers found for the specified location."

        lines: List[str] = []
        for i, center in enumerate(centers, 1):
            center_lines = [f"{i}. {center.get('name', 'SMSA Service Center')}"]
            
            if center.get("address") and center.get("address") != "N/A":
                center_lines.append(f"   Address: {center['address']}")
            
            if center.get("city") and center.get("city") != "N/A":
                center_lines.append(f"   City: {center['city']}")
            
            if center.get("phone") and center.get("phone") != "N/A":
                center_lines.append(f"   Phone: {center['phone']}")
            
            if center.get("hours") and center.get("hours") != "N/A":
                center_lines.append(f"   Hours: {center['hours']}")
            
            lines.append("\n".join(center_lines))

        return "\n\n".join(lines)

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find retail centers based on user query.

        Args:
            context: Contains 'message' and optional 'parameters'

        Returns:
            Dict with 'agent', 'content', and centers data
        """
        message: str = context.get("message", "")
        
        # Extract city from message or parameters
        city = context.get("parameters", {}).get("city")
        if not city:
            city = self._extract_city(message)

        logger.info(
            "retail_request",
            message=message[:100],
            city=city,
            conversation_id=context.get("conversation_id"),
        )

        try:
            result = await self._client.get_retail_centers(city=city, country="SA")
            
            if not result.get("success"):
                error_msg = result.get("error_message", "Unknown error")
                return {
                    "agent": self.name,
                    "content": f"I couldn't retrieve service centers at this time. Error: {error_msg}",
                    "results": [],
                }

            centers = result.get("centers", [])
            
            if not centers:
                location_text = f" in {city}" if city else ""
                return {
                    "agent": self.name,
                    "content": f"No SMSA service centers found{location_text}. Please try a different city or contact SMSA support.",
                    "results": [],
                }

            logger.info(
                "retail_response",
                city=city,
                centers_count=len(centers),
                conversation_id=context.get("conversation_id"),
            )

            # Use LLM to generate user-friendly response
            system_prompt = """You are a helpful AI assistant for SMSA Express service centers.
Generate a friendly, clear, and informative response about SMSA service center locations.
Use the center data provided to answer the user's question naturally and helpfully.
Include important details like address, phone, and hours."""

            import json
            user_message = f"""User asked: {message}

Service centers found:
{json.dumps(centers, indent=2)}

Generate a helpful response about the service centers."""

            try:
                llm_response = await self._llm_client.chat_completion(
                    messages=[{"role": "user", "content": user_message}],
                    system_prompt=system_prompt,
                    temperature=0.7,
                    max_tokens=500,
                )
                content = llm_response.get("content", "").strip()
                
                if not content:
                    # Fallback to formatted response
                    location_text = f" in {city}" if city else ""
                    header = f"Found {len(centers)} SMSA service center(s){location_text}:\n\n"
                    content = header + self._format_centers(centers)
            except Exception as e:
                logger.warning("llm_response_failed", error=str(e))
                # Fallback to formatted response
                location_text = f" in {city}" if city else ""
                header = f"Found {len(centers)} SMSA service center(s){location_text}:\n\n"
                content = header + self._format_centers(centers)

            return {
                "agent": self.name,
                "content": content,
                "results": centers,
            }

        except Exception as e:
            logger.error(
                "retail_error",
                error=str(e),
                conversation_id=context.get("conversation_id"),
                exc_info=True,
            )
            return {
                "agent": self.name,
                "content": "I encountered an error while searching for service centers. Please try again or contact SMSA support.",
                "results": [],
            }


