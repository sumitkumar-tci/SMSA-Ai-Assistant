from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

from ..logging_config import logger
from ..services.smsa_apis import SMSAAIAssistantSMSARatesClient
from ..services.llm_client import SMSAAIAssistantLLMClient
from .base import SMSAAIAssistantBaseAgent


class SMSAAIAssistantRatesAgent(SMSAAIAssistantBaseAgent):
    """
    Agent responsible for shipping rate inquiries.

    Extracts origin/destination/weight/pieces from user message,
    calls SMSA Rates REST API, and formats rate options for display.
    """

    name = "rates"

    def __init__(self) -> None:
        self._client = SMSAAIAssistantSMSARatesClient()
        self._llm_client = SMSAAIAssistantLLMClient()

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
        Shows VAT and total amounts clearly.
        """
        if not result.get("success"):
            error_msg = result.get("error_message") or result.get("errorMessage") or "Unknown error"
            error_code = result.get("error_code") or result.get("errorCode") or "UNKNOWN"
            logger.warning(
                "rates_error",
                error_code=error_code,
                error_message=error_msg,
                result=result,
            )
            return f"I couldn't retrieve rates at the moment: {error_msg}. Please try again later."

        rates = result.get("rates", [])
        if not rates:
            # Empty Data array - this is normal SMSA behavior
            return (
                "Currently no pricing is available for this shipment combination. "
                "You can try changing weight, city, or service type."
            )

        # Format rates for display with VAT and total
        lines = ["Here are the available shipping rates:\n"]
        for rate in rates:
            product = rate.get("product", "Standard Service")
            product_code = rate.get("productCode", "")
            amount = rate.get("amount", 0)
            vat_amount = rate.get("vatAmount", 0)
            total_amount = rate.get("totalAmount", 0)
            vat_percentage = rate.get("vatPercentage", "15%")
            currency = rate.get("currency", "SAR")

            # Format: Product Name (Code): Base Amount + VAT = Total Amount
            lines.append(
                f"• **{product}** ({product_code}):\n"
                f"  Base: {amount:.2f} {currency} + VAT ({vat_percentage}): {vat_amount:.2f} {currency}\n"
                f"  **Total: {total_amount:.2f} {currency}**"
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

        # Determine language from context or default to English
        language = "En"  # Can be enhanced to detect from user preference or message
        
        # Call SMSA Rates API
        result = await self._client.get_rate(
            from_country=rate_params["from_country"],
            to_country=rate_params["to_country"],
            origin_city=rate_params["origin_city"],
            destination_city=rate_params["destination_city"],
            weight=rate_params["weight"],
            pieces=rate_params["pieces"],  # Not used in API but kept for compatibility
            service_type=rate_params["service_type"],  # Not used in API but kept for compatibility
            language=language,
        )

        logger.info(
            "rates_response",
            success=result.get("success"),
            rates_count=len(result.get("rates", [])),
        )

        # Load production-grade prompt
        try:
            prompt_path = Path(__file__).parent.parent / "prompts" / "rates_agent_prompt.txt"
            if prompt_path.exists():
                with open(prompt_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
            else:
                # Fallback prompt if file not found
                system_prompt = """You are a professional shipping rates assistant for SMSA Express.
Provide clear, accurate shipping rate information. Show base amount, VAT, and total for each service option.
Be friendly, concise, and helpful."""
        except Exception as e:
            logger.warning("prompt_load_failed", error=str(e))
            system_prompt = """You are a professional shipping rates assistant for SMSA Express.
Provide clear, accurate shipping rate information."""

        # Build user message with context
        import json
        rates_data = result.get("rates", [])
        
        user_message = f"""User asked: "{message}"

Rate inquiry details:
- Origin: {rate_params['origin_city']}, {rate_params['from_country']}
- Destination: {rate_params['destination_city']}, {rate_params['to_country']}
- Weight: {rate_params['weight']} kg
- Pieces: {rate_params['pieces']}

Rate options from SMSA API:
{json.dumps(rates_data, indent=2) if rates_data else "No rates available for this route."}

Generate a helpful, professional response about these shipping rates. If rates are available, present them clearly with base amount, VAT, and total. If no rates, suggest alternatives."""

        try:
            llm_response = await self._llm_client.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=400,  # Allow more tokens for detailed rate presentation
            )
            content = llm_response.get("content", "").strip()
            
            if not content:
                # Fallback to formatted response
                content = self._format_rate_response(result)
        except Exception as e:
            logger.warning("llm_response_failed", error=str(e))
            # Fallback to formatted response
            content = self._format_rate_response(result)

        return {
            "agent": self.name,
            "content": content,
            "results": result,
        }


