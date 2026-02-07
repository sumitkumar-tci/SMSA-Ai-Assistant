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
        self._inside_thinking = False  # Track if we're inside thinking tags

    def _filter_thinking_content(self, content: str) -> str:
        """
        Filter out thinking tags and content within them using stateful tracking.
        """
        if not content:
            return content
            
        # Check for thinking tag start
        if "<think>" in content.lower():
            self._inside_thinking = True
            # Remove the opening tag and everything after it in this chunk
            content = content[:content.lower().find("<think>")]
            
        # If we're inside thinking tags, filter out all content
        if self._inside_thinking:
            # Check for thinking tag end
            if "</think>" in content.lower():
                self._inside_thinking = False
                # Keep only content after the closing tag
                end_pos = content.lower().find("</think>") + len("</think>")
                content = content[end_pos:]
            else:
                # We're still inside thinking, filter out all content
                return ""
        
        return content
        """
        Clean any remaining reasoning or meta-commentary from the response.
        """
        if not text:
            return text
            
        # Remove common reasoning patterns that might slip through
        reasoning_phrases = [
            "Check if the VAT is calculated correctly.",
            "For SPOP:", "For SSB:",
            "That's correct.",
            "Finally,", "Also,",
            "I should also mention",
            "Make sure the response is concise",
            "Avoid any markdown",
            "Alright, that should cover"
        ]
        
        for phrase in reasoning_phrases:
            text = text.replace(phrase, "")
        
        # Clean up any remaining calculation explanations
        import re
        # Remove calculation patterns like "122.00 * 0.15 = 18.30"
        text = re.sub(r'\d+\.\d+\s*\*\s*0\.\d+\s*=\s*\d+\.\d+,?\s*', '', text)
        
        # Remove "which matches/rounds to" explanations
        text = re.sub(r',?\s*which\s+(matches|rounds\s+to)\s+[^.]*\.', '', text)
        
        # Clean up extra whitespace and newlines
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Multiple newlines to double
        text = text.strip()
        
        return text

    def _clean_reasoning_text(self, text: str) -> str:
        """
        Clean any remaining reasoning or meta-commentary from the response.
        """
        if not text:
            return text
            
        # Remove common reasoning patterns that might slip through
        reasoning_phrases = [
            "Check if the VAT is calculated correctly.",
            "For SPOP:", "For SSB:",
            "That's correct.",
            "Finally,", "Also,",
            "I should also mention",
            "Make sure the response is concise",
            "Avoid any markdown",
            "Alright, that should cover"
        ]
        
        for phrase in reasoning_phrases:
            text = text.replace(phrase, "")
        
        # Clean up any remaining calculation explanations
        import re
        # Remove calculation patterns like "122.00 * 0.15 = 18.30"
        text = re.sub(r'\d+\.\d+\s*\*\s*0\.\d+\s*=\s*\d+\.\d+,?\s*', '', text)
        
        # Remove "which matches/rounds to" explanations
        text = re.sub(r',?\s*which\s+(matches|rounds\s+to)\s+[^.]*\.', '', text)
        
        # Clean up extra whitespace and newlines
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Multiple newlines to double
        text = text.strip()
        
        return text

    def _is_rate_query(self, message: str) -> bool:
        """
        Heuristic check to see if the user is actually asking for shipping rates.

        This prevents us from forcing origin/destination/weight prompts
        on generic greetings like "hi" or small-talk.
        """
        lower_msg = message.lower()
        keywords = [
            "rate",
            "price",
            "cost",
            "shipping",
            "ship",
            "delivery",
            "charges",
        ]
        return any(k in lower_msg for k in keywords)

    def _extract_rate_params(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract rate inquiry parameters from message and context.

        Returns dict with: from_country, to_country, origin_city, destination_city,
        weight, pieces, service_type (optional), and a list of missing_fields.
        """
        # Get parameters from context (extracted by intent classifier)
        params = context.get("parameters", {})
        lower_msg = message.lower()

        # --- Weight extraction ---
        weight = params.get("weight")
        if weight is None:
            # Try to infer from message patterns like "5kg", "5 kg", "0.5 kg"
            # NOTE: this must match real digits, not a literal '\d'
            match = re.search(r"(\d+(\.\d+)?)\s*(kg|kilo|kilogram)s?", lower_msg)
            if match:
                weight = match.group(1)

        # Normalize to string if present
        if weight is not None:
            weight = str(weight)

        # --- Pieces (optional, safe default) ---
        pieces = params.get("pieces") or "1"
        pieces = str(pieces)

        # --- City extraction ---
        origin_city = params.get("origin_city")
        destination_city = params.get("destination_city")

        # Try to extract from message if not in params
        # Use an ordered list so we can respect the order in the user message.
        saudi_cities = [
            "riyadh",
            "jeddah",
            "dammam",
            "khobar",
            "makkah",
            "madinah",
            "taif",
            "abha",
            "jazan",
            "hail",
            "buraidah",
            "tabuk",
            "najran",
            "al jouf",
            "arar",
            "sakaka",
        ]

        # Collect (index, city_name) for each city mention, then sort by index
        found_cities = []
        for city in saudi_cities:
            idx = lower_msg.find(city)
            if idx != -1:
                found_cities.append((idx, city.title()))

        found_cities.sort(key=lambda item: item[0])
        ordered_city_names = [name for _, name in found_cities]

        # Only override/set if we actually detected city names, in message order
        if ordered_city_names:
            if origin_city is None and len(ordered_city_names) >= 1:
                origin_city = ordered_city_names[0]
            if destination_city is None and len(ordered_city_names) >= 2:
                destination_city = ordered_city_names[1]

        # Extract service type if mentioned (optional contextual hint)
        service_type = None
        if "dlv" in lower_msg or "delivery" in lower_msg:
            service_type = "DLV"
        elif "exp" in lower_msg or "express" in lower_msg:
            service_type = "EXP"

        # Track missing required fields so we can ask the user explicitly
        missing_fields = []
        if origin_city is None:
            missing_fields.append("origin_city")
        if destination_city is None:
            missing_fields.append("destination_city")
        if weight is None:
            missing_fields.append("weight")

        return {
            "from_country": "SA",
            "to_country": "SA",
            "origin_city": origin_city,
            "destination_city": destination_city,
            "weight": weight,
            "pieces": pieces,
            "service_type": service_type,
            "missing_fields": missing_fields,
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

    async def run_stream(self, context: Dict[str, Any]):
        """Execute rates agent with streaming support."""
        import json

        # Reset thinking state for new request
        self._inside_thinking = False
        
        message: str = context["message"]

        # If this is not clearly a rates question, handle conversationally via LLM
        if not self._is_rate_query(message):
            logger.info(
                "rates_conversational_request",
                message_preview=message[:100],
                conversation_id=context.get("conversation_id"),
            )
            # Load system prompt (same as for normal rates, but used for generic help)
            try:
                prompt_path = (
                    Path(__file__).parent.parent / "prompts" / "rates_agent_prompt.txt"
                )
                if prompt_path.exists():
                    with open(prompt_path, "r", encoding="utf-8") as f:
                        system_prompt = f.read()
                else:
                    system_prompt = (
                        "You are a professional shipping rates assistant for SMSA Express. "
                        "Greet the user, briefly explain you can help with shipping rates inside Saudi Arabia, "
                        "and then ask them for origin city, destination city, and weight in kg."
                    )
            except Exception as e:
                logger.warning("rates_prompt_load_failed", error=str(e))
                system_prompt = (
                    "You are a professional shipping rates assistant for SMSA Express. "
                    "Respond directly to customers without showing any reasoning or thinking process. "
                    "Be concise, friendly, and ask for origin city, destination city, and weight in kg when needed. "
                    "Use plain text format only, no markdown."
                )

            try:
                chunk_count = 0
                async for chunk in self._llm_client.chat_completion_stream(
                    messages=[{"role": "user", "content": message}],
                    system_prompt=system_prompt,
                    temperature=0.3,  # Lower temperature for more consistent responses
                    max_tokens=200,
                ):
                    chunk_count += 1
                    content = chunk.get("content", "") or ""

                    # --- Stateful thinking filter ---
                    content = self._filter_thinking_content(content)
                    
                    # --- Additional reasoning filter ---
                    if content:
                        lower = content.lower().strip()

                        # Skip obvious reasoning/meta sentences - expanded list
                        reasoning_patterns = [
                            "the user", "according to", "the guidelines", "i should respond",
                            "let me", "first,", "maybe", "the rules", "the example",
                            "let me check", "let me see", "i need to", "i have to",
                            "my response should", "i should make sure", "i'll draft",
                            "need to keep it concise", "looking back", "wait,", "okay,",
                            "alright,", "i'll follow", "following the", "as specified",
                            "check if", "make sure", "that covers", "it's concise",
                            "friendly,", "professional,", "within 2-3 sentences",
                            "avoid any markdown", "just plain text", "with bullets",
                            "finally,", "also,", "since there are", "i should also",
                            "the currency is", "all numbers are", "the format",
                            "as a template", "the response should be", "maybe start with",
                            "end with", "offer to help", "further assistance"
                        ]
                        if any(pat in lower for pat in reasoning_patterns):
                            continue

                        # Skip very short filler like "okay" etc. at the start of stream
                        if chunk_count < 20 and lower in {"okay", "alright", "hmm", "well", "let's see"}:
                            continue

                        # Skip lines that are clearly meta-commentary about the response
                        if any(phrase in lower for phrase in [
                            "that should cover", "this covers all", "make sure the response",
                            "the user might", "i should mention", "i need to make sure"
                        ]):
                            continue

                    # If we get here, content is safe to show
                    if content:
                        # DON'T apply heavy text cleaning to individual streaming chunks
                        # Just yield the content as-is to preserve spacing
                        yield {
                            "type": "token",
                            "content": content,
                            "metadata": {
                                "agent": self.name,
                                "type": "conversational",
                            },
                        }
            except Exception as e:
                logger.warning("rates_conversational_stream_failed", error=str(e))
                fallback = (
                    "Hi, I can help you with SMSA shipping rates inside Saudi Arabia. "
                    "Please tell me the origin city, destination city, and weight in kilograms "
                    "for your shipment (for example: 'Rate for 1 kg from Riyadh to Jeddah')."
                )
                yield {
                    "type": "token",
                    "content": fallback,
                    "metadata": {
                        "agent": self.name,
                        "type": "conversational",
                    },
                }
            return

        # Extract parameters and identify missing required fields
        rate_params = self._extract_rate_params(message, context)
        missing_fields = rate_params.get("missing_fields", [])

        # If required information is missing, DO NOT call the API.
        if missing_fields:
            field_labels = {
                "origin_city": "origin city",
                "destination_city": "destination city",
                "weight": "weight (in kg)",
            }
            missing_names = [
                field_labels[f] for f in missing_fields if f in field_labels
            ]
            missing_text = ", ".join(missing_names)
            prompt = (
                "To get accurate shipping rates, I need a bit more information. "
                f"Please provide the following: {missing_text}. "
                "For example: 'Rate for 5 kg from Riyadh to Jeddah'."
            )
            yield {
                "type": "token",
                "content": prompt,
                "metadata": {
                    "agent": self.name,
                    "requires_parameters": missing_fields,
                },
            }
            return

        logger.info(
            "rates_request",
            origin_city=rate_params["origin_city"],
            destination_city=rate_params["destination_city"],
            weight=rate_params["weight"],
            conversation_id=context.get("conversation_id"),
        )

        # Determine language from context or default to English
        language = "En"
        
        # Call SMSA Rates API (fast, ~1-2 seconds)
        result = await self._client.get_rate(
            from_country=rate_params["from_country"],
            to_country=rate_params["to_country"],
            origin_city=rate_params["origin_city"],
            destination_city=rate_params["destination_city"],
            weight=rate_params["weight"],
            pieces=rate_params["pieces"],
            service_type=rate_params["service_type"],
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
                system_prompt = """You are a professional shipping rates assistant for SMSA Express.
Provide clear, accurate shipping rate information. Show base amount, VAT, and total for each service option.
Be friendly, concise, and helpful."""
        except Exception as e:
            logger.warning("prompt_load_failed", error=str(e))
            system_prompt = """You are a professional shipping rates assistant for SMSA Express.
Provide clear, accurate shipping rate information."""

        # Build user message with context
        rates_data = result.get("rates", [])
        
        user_message = f"""User asked: "{message}"

Rate inquiry details:
- Origin: {rate_params['origin_city']}, {rate_params['from_country']}
- Destination: {rate_params['destination_city']}, {rate_params['to_country']}
- Weight: {rate_params['weight']} kg
- Pieces: {rate_params['pieces']}

Rate options from SMSA API:
{json.dumps(rates_data, indent=2) if rates_data else "No rates available for this route."}

IMPORTANT: Respond directly to the customer. Do not show any thinking process, reasoning, or meta-commentary. Use plain text format only (no markdown). Present rates clearly with base amount, VAT, and total. Be concise and professional."""

        try:
            # Stream LLM response
            async for chunk in self._llm_client.chat_completion_stream(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for more consistent responses
                max_tokens=400,
            ):
                content = chunk.get("content", "")
                if content:
                    # Apply stateful thinking filter first
                    content = self._filter_thinking_content(content)
                    # For streaming, don't apply heavy text cleaning that removes spaces
                    # Just yield the filtered content to preserve proper spacing
                    if content:  # Only yield if there's still content after filtering
                        yield {
                            "type": "token",
                            "content": content,
                            "metadata": {
                                "agent": self.name,
                                "results": result,
                            },
                        }
        except Exception as e:
            logger.warning("llm_stream_failed", error=str(e))
            # Fallback to formatted response
            content = self._format_rate_response(result)
            yield {
                "type": "token",
                "content": content,
                "metadata": {
                    "agent": self.name,
                    "results": result,
                },
            }

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        message: str = context["message"]

        # If this is not clearly a rates question, handle conversationally via LLM
        if not self._is_rate_query(message):
            logger.info(
                "rates_conversational_request",
                message_preview=message[:100],
                conversation_id=context.get("conversation_id"),
            )
            try:
                prompt_path = (
                    Path(__file__).parent.parent / "prompts" / "rates_agent_prompt.txt"
                )
                if prompt_path.exists():
                    with open(prompt_path, "r", encoding="utf-8") as f:
                        system_prompt = f.read()
                else:
                    system_prompt = (
                        "You are a professional shipping rates assistant for SMSA Express. "
                        "Greet the user, briefly explain you can help with shipping rates inside Saudi Arabia, "
                        "and then ask them for origin city, destination city, and weight in kg."
                    )
            except Exception as e:
                logger.warning("rates_prompt_load_failed", error=str(e))
                system_prompt = (
                    "You are a professional shipping rates assistant for SMSA Express. "
                    "Respond directly to customers without showing any reasoning or thinking process. "
                    "Be concise, friendly, and ask for origin city, destination city, and weight in kg when needed. "
                    "Use plain text format only, no markdown."
                )

            try:
                llm_response = await self._llm_client.chat_completion(
                    messages=[{"role": "user", "content": message}],
                    system_prompt=system_prompt,
                    temperature=0.3,  # Lower temperature for more consistent responses
                    max_tokens=200,
                )
                content = llm_response.get("content", "").strip()
                if not content:
                    content = (
                        "Hi, I can help you with SMSA shipping rates inside Saudi Arabia. "
                        "Please share the origin city, destination city, and weight in kilograms "
                        "for your shipment (for example: 'Rate for 1 kg from Riyadh to Jeddah')."
                    )
            except Exception as e:
                logger.warning("rates_conversational_response_failed", error=str(e))
                content = (
                    "Hi, I can help you with SMSA shipping rates inside Saudi Arabia. "
                    "Please share the origin city, destination city, and weight in kilograms "
                    "for your shipment (for example: 'Rate for 1 kg from Riyadh to Jeddah')."
                )

            return {
                "agent": self.name,
                "content": content,
                "results": {
                    "success": False,
                    "errorCode": "CONVERSATIONAL_ONLY",
                    "errorMessage": "Greeting / non-rate message handled conversationally.",
                },
            }

        # Extract parameters and identify missing required fields
        rate_params = self._extract_rate_params(message, context)
        missing_fields = rate_params.get("missing_fields", [])

        # If required information is missing, DO NOT call the API.
        if missing_fields:
            field_labels = {
                "origin_city": "origin city",
                "destination_city": "destination city",
                "weight": "weight (in kg)",
            }
            missing_names = [
                field_labels[f] for f in missing_fields if f in field_labels
            ]
            missing_text = ", ".join(missing_names)
            prompt = (
                "To get accurate shipping rates, I need some more details. "
                f"Please provide the following: {missing_text}. "
                "For example: 'Rate for 5 kg from Riyadh to Jeddah'."
            )
            return {
                "agent": self.name,
                "content": prompt,
                "results": {
                    "success": False,
                    "errorCode": "MISSING_PARAMETERS",
                    "errorMessage": f"Missing required fields: {missing_text}",
                },
            }

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

IMPORTANT: Respond directly to the customer. Do not show any thinking process, reasoning, or meta-commentary. Use plain text format only (no markdown). Present rates clearly with base amount, VAT, and total. Be concise and professional."""

        try:
            llm_response = await self._llm_client.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for more consistent responses
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


