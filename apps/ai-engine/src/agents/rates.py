from __future__ import annotations

import re
from typing import Any, Dict

from ..logging_config import logger
from ..services.smsa_apis import SMSARatesClient
from .base import BaseAgent


class RatesAgent(BaseAgent):
    """
    Agent responsible for shipping rate inquiries.

    Extracts origin/destination/weight/pieces from user message,
    calls SMSA Rates REST API, and formats rate options for display.
    """

    name = "rates"

    def __init__(self) -> None:
        self._client = SMSARatesClient()

    def _extract_rate_params(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract rate inquiry parameters from message and context.

        Returns dict with: from_country, to_country, origin_city, destination_city,
        weight, pieces, service_type (optional).
        """
        # Get parameters from context (extracted by intent classifier)
        params = context.get("parameters", {})
        lower_msg = message.lower()

        # Extract weight (default to "1" if not found)
        weight = params.get("weight") or "1"
        # Ensure it's a string
        weight = str(weight)

        # Extract pieces (default to "1" if not found)
        pieces = params.get("pieces") or "1"
        pieces = str(pieces)

        # Extract cities
        origin_city = params.get("origin_city") or "Riyadh"  # Default to Riyadh
        destination_city = params.get("destination_city") or "Jeddah"  # Default to Jeddah

        # Try to extract from message if not in params
        saudi_cities = {
            "riyadh", "jeddah", "dammam", "khobar", "makkah", "madinah",
            "taif", "abha", "jazan", "hail", "buraidah", "tabuk",
            "najran", "al jouf", "arar", "sakaka"
        }

        found_cities = []
        for city in saudi_cities:
            if city in lower_msg:
                found_cities.append(city.title())

        if len(found_cities) >= 2:
            origin_city = found_cities[0]
            destination_city = found_cities[1]
        elif len(found_cities) == 1:
            destination_city = found_cities[0]

        # Extract service type if mentioned
        service_type = None
        if "dlv" in lower_msg or "delivery" in lower_msg:
            service_type = "DLV"
        elif "exp" in lower_msg or "express" in lower_msg:
            service_type = "EXP"

        return {
            "from_country": "SA",
            "to_country": "SA",
            "origin_city": origin_city,
            "destination_city": destination_city,
            "weight": weight,
            "pieces": pieces,
            "service_type": service_type,
        }

    def _format_rate_response(self, result: Dict[str, Any]) -> str:
        """
        Format rate API response into user-friendly message.

        Handles empty Data array gracefully as per SMSA API behavior.
        """
        if not result.get("success"):
            error_msg = result.get("error_message", "Unknown error")
            return f"I couldn't retrieve rates at the moment: {error_msg}. Please try again later."

        rates = result.get("rates", [])
        if not rates:
            # Empty Data array - this is normal SMSA behavior
            return (
                "Currently no pricing is available for this shipment combination. "
                "You can try changing weight, city, or service type."
            )

        # Format rates for display
        lines = ["Here are the available shipping rates:\n"]
        for rate in rates:
            service_name = rate.get("serviceName", rate.get("service", "Standard"))
            amount = rate.get("amount", "N/A")
            currency = rate.get("currency", "SAR")
            eta = rate.get("eta", "N/A")

            lines.append(
                f"• {service_name}: {amount} {currency} (Estimated: {eta} days)"
            )

        return "\n".join(lines)

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        message: str = context["message"]

        # Extract parameters
        rate_params = self._extract_rate_params(message, context)

        logger.info(
            "rates_request",
            origin_city=rate_params["origin_city"],
            destination_city=rate_params["destination_city"],
            weight=rate_params["weight"],
            conversation_id=context.get("conversation_id"),
        )

        # Call SMSA Rates API
        result = await self._client.get_rate(
            from_country=rate_params["from_country"],
            to_country=rate_params["to_country"],
            origin_city=rate_params["origin_city"],
            destination_city=rate_params["destination_city"],
            weight=rate_params["weight"],
            pieces=rate_params["pieces"],
            service_type=rate_params["service_type"],
        )

        # Format response
        content = self._format_rate_response(result)

        logger.info(
            "rates_response",
            success=result.get("success"),
            rates_count=len(result.get("rates", [])),
        )

        return {
            "agent": self.name,
            "content": content,
            "results": result,
        }


