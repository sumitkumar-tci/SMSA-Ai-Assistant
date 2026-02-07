from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from ..logging_config import logger
from ..services.smsa_apis import SMSAAIAssistantSMSARetailCentersClient
from ..services.llm_client import SMSAAIAssistantLLMClient
from .base import SMSAAIAssistantBaseAgent


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two lat/long coordinates using Haversine formula.
    Returns distance in kilometers.
    """
    if not all([lat1, lon1, lat2, lon2]):
        return float('inf')
    
    # Radius of Earth in kilometers
    R = 6371.0
    
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance


class SMSAAIAssistantRetailCentersAgent(SMSAAIAssistantBaseAgent):
    """
    Agent for finding SMSA retail/service centers with geo-location intelligence.
    
    Handles three input types:
    1. Post Code → Identify city → Get centers → Filter nearest
    2. Area Name → Check if multiple cities → Ask if ambiguous → Filter nearest
    3. City Name → Get all centers → Filter by area/post code if provided
    
    Returns top 5-10 nearest centers based on distance calculation.
    """

    name = "retail_centers"

    # Common Saudi cities
    SAUDI_CITIES = [
        "riyadh", "jeddah", "dammam", "khobar", "makkah", "madinah",
        "taif", "abha", "jazan", "hail", "buraidah", "tabuk",
        "najran", "al jouf", "arar", "sakaka", "qassim", "yanbu",
    ]

    # Common Saudi area coordinates (area_name -> (lat, lon))
    # These are approximate coordinates for major areas
    SAUDI_AREAS = {
        # Riyadh areas
        "olaya": (24.61, 46.70),
        "malaz": (24.64, 46.72),
        "batha": (24.64, 46.72),
        "diriyah": (24.74, 46.57),
        "al malaz": (24.64, 46.72),
        "al olaya": (24.61, 46.70),
        "king fahd": (24.65, 46.71),
        "king fahd road": (24.65, 46.71),
        "king abdulaziz": (24.63, 46.69),
        "sultanah": (24.60, 46.69),
        "sultanah swaidi": (24.60, 46.69),
        "mansourah": (24.64, 46.62),
        "dhahrat laban": (24.65, 46.75),
        "marqab": (24.65, 46.72),
        "diriya": (24.74, 46.57),
        "mahdiyah": (24.64, 46.75),
        # Jeddah areas
        "corniche": (21.49, 39.18),
        "al balad": (21.49, 39.19),
        "al hamra": (21.50, 39.18),
        "al rawdah": (21.52, 39.17),
        # Dammam/Khobar areas
        "corniche dammam": (26.42, 50.10),
        "al khobar": (26.28, 50.20),
    }

    # City center coordinates (city_name -> (lat, lon))
    SAUDI_CITY_CENTERS = {
        "riyadh": (24.65, 46.77),
        "jeddah": (21.49, 39.19),
        "dammam": (26.42, 50.10),
        "khobar": (26.28, 50.20),
        "makkah": (21.39, 39.86),
        "madinah": (24.47, 39.61),
        "taif": (21.27, 40.42),
        "abha": (18.22, 42.51),
        "jazan": (16.89, 42.56),
        "hail": (27.52, 41.70),
        "buraidah": (26.33, 43.97),
        "tabuk": (28.40, 36.58),
    }

    def __init__(self) -> None:
        super().__init__()
        self._client = SMSAAIAssistantSMSARetailCentersClient()
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
            "Alright, that should cover",
            "Let me check", "Let me see",
            "I need to", "I have to",
            "The user asked", "According to",
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

    def _is_conversational_query(self, message: str) -> bool:
        """
        Check if the user is asking a conversational question rather than looking for service centers.
        
        This prevents simple greetings from triggering location searches.
        """
        lower_msg = message.lower().strip()
        
        # Simple greetings - check if message STARTS with or CONTAINS these
        greeting_starters = [
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "greetings", "salaam", "salam"
        ]
        
        # Check if message starts with any greeting
        for greeting in greeting_starters:
            if lower_msg.startswith(greeting):
                return True
        
        # Check for "how are you" anywhere in the message
        if "how are you" in lower_msg:
            return True
            
        # Check for other conversational phrases
        conversational_phrases = [
            "what's up", "how you doing", "how are you doing", "how's it going",
            "good to see you", "nice to meet you", "pleasure to meet you"
        ]
        
        for phrase in conversational_phrases:
            if phrase in lower_msg:
                return True
        
        # Questions about capabilities
        capability_questions = [
            "what can you do", "how can you help", "what do you do", "help me",
            "what are your capabilities", "what services", "how does this work",
            "what is this", "who are you", "what are you"
        ]
        if any(q in lower_msg for q in capability_questions):
            return True
        
        # General questions without location keywords
        location_keywords = [
            "center", "centres", "branch", "office", "location", "address", "near",
            "city", "area", "post code", "postal code", "zip", "find", "search",
            "riyadh", "jeddah", "dammam", "khobar", "makkah", "madinah"
        ]
        
        # If message is very short and has no location keywords, it's likely conversational
        if len(lower_msg.split()) <= 5 and not any(keyword in lower_msg for keyword in location_keywords):
            return True
        
        return False

    def _extract_center_count(self, message: str) -> int:
        """
        Extract the number of centers requested by the user.
        Returns the requested count or default of 5.
        """
        lower_msg = message.lower()
        
        # Look for patterns like "5 centers", "show 3", "find 10 centers", etc.
        patterns = [
            r'(\d+)\s*centers?',
            r'(\d+)\s*centres?',
            r'show\s*(\d+)',
            r'find\s*(\d+)',
            r'get\s*(\d+)',
            r'(\d+)\s*only',
            r'top\s*(\d+)',
            r'first\s*(\d+)',
            r'(\d+)\s*nearest',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, lower_msg)
            if match:
                try:
                    count = int(match.group(1))
                    # Reasonable limits: minimum 1, maximum 20
                    if 1 <= count <= 20:
                        return count
                except ValueError:
                    continue
        
        # Default to 5 centers if no specific number requested
        return 5

    async def run_stream(self, context: Dict[str, Any]):
        """
        Streaming variant of the retail centers agent with proper LLM streaming.
        """
        # Reset thinking state for new request
        self._inside_thinking = False
        
        message: str = context.get("message", "")
        
        # Check if this is a simple greeting or conversational query (not location-based)
        if self._is_conversational_query(message):
            logger.info("retail_conversational_request", message_preview=message[:100])
            
            # Use LLM for conversational responses
            system_prompt = """You are a helpful AI assistant for SMSA Express service centers.

CRITICAL: Do NOT use any thinking tags like <think>, </think>, <reasoning>, or </reasoning>. 
Respond directly to customers without showing any internal reasoning or thought process.

You help customers find SMSA service centers and retail locations. 
For greetings, respond warmly and explain how you can help.
For questions about services, provide helpful information.
Keep responses concise and friendly.
Use plain text format only, no markdown formatting.

Examples:
- User: "Hi" → "Hello! I'm here to help you find SMSA Express service centers. You can ask me to find centers by city, area, or post code. How can I assist you?"
- User: "What can you do?" → "I can help you locate SMSA Express service centers across Saudi Arabia and other countries. Just tell me your city, area, or post code and I'll find the nearest centers for you."
"""
            
            try:
                # Stream LLM response
                chunk_count = 0
                async for chunk in self._llm_client.chat_completion_stream(
                    messages=[{"role": "user", "content": message}],
                    system_prompt=system_prompt,
                    temperature=0.3,  # Lower temperature for more consistent responses
                    max_tokens=200,
                ):
                    chunk_count += 1
                    content = chunk.get("content", "")
                    
                    # Apply stateful thinking filter first
                    content = self._filter_thinking_content(content)
                    
                    # Additional reasoning filter for streaming
                    if content:
                        content_lower = content.lower().strip()
                        reasoning_patterns = [
                            "hi, the user", "the user sent", "according to", "the guidelines", 
                            "i should respond", "i should", "let me", "okay,", "alright,", 
                            "first,", "maybe", "the rules", "let me check", "let me make sure", 
                            "i'll structure", "the response should", "no need to mention",
                            "just a straightforward", "the main thing is", "should i point",
                            "probably not", "just respond as if", "keep it friendly",
                            "yes, the example", "make sure to use", "just follow the script",
                            "provided in the rules"
                        ]
                        
                        # Skip if content contains reasoning patterns
                        if any(pattern in content_lower for pattern in reasoning_patterns):
                            continue
                        
                        # Skip if content is just reasoning words or phrases
                        reasoning_words = ["okay", "alright", "yes", "no", "hmm", "well", "so"]
                        if content_lower.strip() in reasoning_words and chunk_count < 20:
                            continue
                        
                        # Skip very long sentences that look like reasoning (over 100 chars and contains reasoning keywords)
                        if len(content) > 100 and any(word in content_lower for word in ["guidelines", "rules", "should", "need to", "according"]):
                            continue
                    
                    # Only yield if content is not empty and not reasoning
                    if content:
                        yield {
                            "type": "token",
                            "content": content,
                            "metadata": {
                                "agent": self.name,
                                "type": "conversational",
                                "centers": [],
                                "location_info": None,
                                "city": None,
                                "needs_clarification": False,
                            },
                        }
                        
            except Exception as e:
                logger.warning("retail_conversational_stream_failed", error=str(e))
                fallback = "Hello! I'm here to help you find SMSA Express service centers. You can ask me to find centers by city, area, or post code. How can I assist you?"
                yield {
                    "type": "token",
                    "content": fallback,
                    "metadata": {
                        "agent": self.name,
                        "type": "conversational",
                        "centers": [],
                        "location_info": None,
                        "city": None,
                        "needs_clarification": False,
                    },
                }
            return
        
        # For location-based queries, do the work ONCE (no double processing)
        # Extract requested count first
        requested_count = self._extract_center_count(message)
        
        # Quick location classification with fallback
        logger.info("retail_classifying_location", message=message)
        
        # Simple fallback: if message contains "riyadh", use it directly
        lower_msg = message.lower()
        if "riyadh" in lower_msg:
            location_info = {
                "city_name": "Riyadh",
                "location_type": "city_name",
                "needs_clarification": False
            }
            logger.info("retail_location_fallback", location_info=location_info)
        else:
            location_info = await self._classify_location_with_llm(message)
            logger.info("retail_location_classified", location_info=location_info)
        
        if location_info.get("needs_clarification"):
            clarification_question = location_info.get("clarification_question") or \
                "I need more information about your location. Could you please specify the city or area?"
            
            # Stream clarification directly (no LLM delay)
            for char in clarification_question:
                if char:
                    yield {
                        "type": "token",
                        "content": char,
                        "metadata": {
                            "agent": self.name,
                            "type": "conversational",
                            "centers": [],
                            "location_info": location_info,
                            "city": None,
                            "needs_clarification": True,
                        },
                    }
            return
        
        # Get city and fetch centers (main API work)
        city = location_info.get("city_name") or "Riyadh"
        logger.info("retail_fetching_centers", city=city, location_info=location_info)
        result = await self._client.list_of_centers(city=city, country="SA")
        logger.info("retail_api_result", success=result.get("success"), centers_count=len(result.get("centers", [])), error=result.get("error_message"))
        
        if not result.get("success") or not result.get("centers"):
            error_msg = f"I couldn't find any SMSA service centers in {city}. Please try a different city or contact SMSA support."
            # Add more specific error information
            if result.get("error_message"):
                error_msg = f"I encountered an issue while searching for centers in {city}: {result.get('error_message')}. Please try again or contact SMSA support."
            
            for char in error_msg:
                if char:
                    yield {
                        "type": "token",
                        "content": char,
                        "metadata": {
                            "agent": self.name,
                            "type": "error",
                            "centers": [],
                            "location_info": location_info,
                            "city": city,
                        },
                    }
            return
        
        # Process and limit centers
        centers = result.get("centers", [])
        reference_lat, reference_lon = await self._get_user_location_coords(location_info, city=city)
        centers = self._calculate_distances(centers, reference_lat, reference_lon)
        
        if reference_lat and reference_lon:
            centers = self._filter_nearest_centers(centers, max_results=max(requested_count, 10))
        else:
            centers = centers[:max(requested_count, 10)]
        
        # Limit to exactly what user requested
        limited_centers = centers[:requested_count]
        
        # Create clean, well-formatted response with explicit formatting
        response_parts = []
        response_parts.append(f"Here are {len(limited_centers)} SMSA service centers in {city}:")
        response_parts.append("")  # Empty line
        
        for i, center in enumerate(limited_centers, 1):
            # Extract and clean center data
            name = center.get("name", center.get("centerName", "SMSA Center"))
            address = center.get("address", center.get("fullAddress", "Address not available"))
            phone = center.get("phone", center.get("phoneNumber", "920009999"))
            distance = center.get("distance_km")
            hours = center.get("workingHours", center.get("hours", "8:00-23:00 (Saturday to Thursday)"))
            
            # Build center info as a block
            center_block = f"{i}. {name}\n"
            center_block += f"   Address: {address}\n"
            center_block += f"   Phone: {phone}\n"
            if distance and distance > 0:
                center_block += f"   Distance: {distance:.2f} km\n"
            if hours and hours != "Address not available":
                center_block += f"   Hours: {hours}\n"
            
            response_parts.append(center_block.rstrip())  # Remove trailing newline
            response_parts.append("")  # Empty line between centers
        
        response_parts.append("Need more details about any center? Just let me know!")
        
        # Stream each part separately to preserve formatting
        for part in response_parts:
            if part == "":
                # Send empty line
                yield {
                    "type": "token", 
                    "content": "\n",
                    "metadata": {
                        "agent": self.name,
                        "type": "location_result",
                        "centers": limited_centers,
                        "location_info": location_info,
                        "city": city,
                        "needs_clarification": False,
                        "requested_count": requested_count,
                    },
                }
            else:
                # Send content with newline
                yield {
                    "type": "token", 
                    "content": part + "\n",
                    "metadata": {
                        "agent": self.name,
                        "type": "location_result",
                        "centers": limited_centers,
                        "location_info": location_info,
                        "city": city,
                        "needs_clarification": False,
                        "requested_count": requested_count,
                    },
                }

    def _extract_location_info(self, message: str) -> Dict[str, Any]:
        """
        Extract location information from user message.
        Returns dict with: post_code, area_name, city_name, location_type
        """
        message_lower = message.lower()
        
        # Check for post code (1-5 digit Saudi post codes, e.g., "357", "12345")
        post_code_match = re.search(r'\b\d{1,5}\b', message)
        post_code = post_code_match.group() if post_code_match else None
        
        # Extract city name
        city_name = None
        for city in self.SAUDI_CITIES:
            if city in message_lower:
                city_name = city.title()
                break
        
        # Extract area name (heuristic: words that might be area names)
        # This is a simple heuristic - LLM will refine this
        area_name = None
        if not post_code and not city_name:
            # Try to identify area-like words (2-3 words, not common stop words)
            words = message_lower.split()
            stop_words = {"in", "near", "close", "to", "find", "centers", "retail", "service", "smsa"}
            area_candidates = [w for w in words if w not in stop_words and len(w) > 3]
            if area_candidates:
                area_name = " ".join(area_candidates[:2])  # Take first 2 words
        
        location_type = None
        if post_code:
            location_type = "post_code"
        elif area_name:
            location_type = "area_name"
        elif city_name:
            location_type = "city_name"
        
        return {
            "post_code": post_code,
            "area_name": area_name,
            "city_name": city_name,
            "location_type": location_type,
        }

    async def _classify_query_intent(self, message: str) -> Dict[str, Any]:
        """
        Classify the query intent to determine which API to call.
        Returns dict with:
        - "intent_type": "countries" | "cities" | "retail_cities" | "center_by_code" | "location_based"
        - "center_code": extracted center code if intent_type is "center_by_code"
        - "country": extracted country code if needed (defaults to "SA")
        """
        message_lower = message.lower()
        
        # Quick heuristic checks first (faster than LLM)
        # Check for countries query
        countries_keywords = ["countries", "country", "list countries", "show countries", "available countries"]
        if any(keyword in message_lower for keyword in countries_keywords):
            return {
                "intent_type": "countries",
                "center_code": None,
                "country": "SA",
            }
        
        # Check for cities query (not retail cities)
        cities_keywords = ["cities in", "list cities", "show cities", "what cities", "cities are"]
        retail_cities_keywords = ["retail cities", "cities have retail", "cities with retail", "retail centers cities"]
        
        if any(keyword in message_lower for keyword in retail_cities_keywords):
            # Extract country code if mentioned
            country = "SA"  # Default
            if "uae" in message_lower or "united arab emirates" in message_lower:
                country = "AE"
            elif "kuwait" in message_lower:
                country = "KW"
            elif "bahrain" in message_lower:
                country = "BH"
            elif "oman" in message_lower:
                country = "OM"
            
            return {
                "intent_type": "retail_cities",
                "center_code": None,
                "country": country,
            }
        
        if any(keyword in message_lower for keyword in cities_keywords):
            # Extract country code if mentioned
            country = "SA"  # Default
            if "uae" in message_lower or "united arab emirates" in message_lower:
                country = "AE"
            elif "kuwait" in message_lower:
                country = "KW"
            elif "bahrain" in message_lower:
                country = "BH"
            elif "oman" in message_lower:
                country = "OM"
            
            return {
                "intent_type": "cities",
                "center_code": None,
                "country": country,
            }
        
        # Check for center code query
        # Priority: If "center code" is mentioned, it's definitely a center code query
        if "center code" in message_lower:
            # Extract code after "center code"
            code_match = re.search(r'center\s+code\s+([A-Z0-9]+)', message_lower, re.IGNORECASE)
            if code_match:
                code = code_match.group(1).upper()
                return {
                    "intent_type": "center_by_code",
                    "center_code": code,
                    "country": "SA",
                }
        
        # Check for patterns that indicate center code (not post code)
        center_code_patterns = [
            r"code\s+([A-Z]{3}\d+)",  # Pattern like "RUH001"
            r"center\s+([A-Z]{3}\d+)",  # Pattern like "center RUH001"
            r"details for center\s+([A-Z0-9]+)",  # "details for center RUH001"
            r"show me center\s+([A-Z0-9]+)",  # "show me center RUH001"
        ]
        
        for pattern in center_code_patterns:
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                code = match.group(1).upper()
                # Check if it looks like a center code (alphanumeric pattern like RUH001)
                if re.match(r'^[A-Z]{3}\d+$', code):
                    return {
                        "intent_type": "center_by_code",
                        "center_code": code,
                        "country": "SA",
                    }
        
        # Check for "code" followed by alphanumeric (but not "post code")
        if "code" in message_lower and "post code" not in message_lower and "postal code" not in message_lower:
            # Extract code after "code" (but not if it's clearly a post code context)
            code_match = re.search(r'\bcode\s+([A-Z0-9]+)', message_lower, re.IGNORECASE)
            if code_match:
                code = code_match.group(1).upper()
                # If it's alphanumeric (not just digits), treat as center code
                # If it's just digits and short (1-5 digits), might be post code, skip
                if not code.isdigit() or (code.isdigit() and len(code) > 5):
                    return {
                        "intent_type": "center_by_code",
                        "center_code": code,
                        "country": "SA",
                    }
        
        # Use LLM for more complex classification
        system_prompt = """You are a query intent classifier for SMSA Express retail centers API.
Analyze the user's message and determine what type of query it is.
Return ONLY a JSON object with these fields:
- "intent_type": one of "countries", "cities", "retail_cities", "center_by_code", or "location_based"
- "center_code": center code if intent_type is "center_by_code" (e.g., "RUH001", "RUH002"), null otherwise
- "country": country code if needed (e.g., "SA", "AE", "KW"), defaults to "SA"

Intent types:
- "countries": User wants to see all countries where SMSA operates (e.g., "What countries are available?", "List all countries")
- "cities": User wants to see all cities in a country (e.g., "What cities are in Saudi Arabia?", "List cities in SA")
- "retail_cities": User wants to see cities that have retail centers (e.g., "Which cities have retail centers?", "Retail cities in SA")
- "center_by_code": User wants details for a specific center by its code (e.g., "Show me center code RUH001", "Details for center 357")
- "location_based": User wants to find centers near a location (e.g., "Find centers in Riyadh", "I'm in Olaya", "Near post code 357")

Important:
- If user mentions "center code" or "code" with a value, it's "center_by_code"
- If user mentions "post code" or "postal code", it's "location_based"
- If user asks about "countries", it's "countries"
- If user asks about "cities" with "retail", it's "retail_cities"
- If user asks about "cities" without "retail", it's "cities"
- Everything else is "location_based"

Return ONLY the JSON object, no other text."""

        try:
            llm_response = await self._llm_client.chat_completion(
                messages=[{"role": "user", "content": message}],
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=200,
            )
            
            content = llm_response.get("content", "").strip()
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                import json
                result = json.loads(json_match.group())
                # Validate intent_type
                valid_intents = ["countries", "cities", "retail_cities", "center_by_code", "location_based"]
                if result.get("intent_type") not in valid_intents:
                    result["intent_type"] = "location_based"  # Default fallback
                return result
        except Exception as e:
            logger.warning("query_intent_classification_failed", error=str(e))
        
        # Default fallback: assume location-based query
        return {
            "intent_type": "location_based",
            "center_code": None,
            "country": "SA",
        }

    async def _classify_location_with_llm(self, message: str) -> Dict[str, Any]:
        """
        Use LLM to classify location information from user message.
        Returns structured location data.
        """
        system_prompt = """You are a location classification assistant for SMSA Express.
Analyze the user's message and extract location information.
Return ONLY a JSON object with these fields:
- "post_code": post code if mentioned (1-5 digits, e.g., "357", "12345"), null otherwise
- "area_name": area/neighborhood name if mentioned, null otherwise
- "city_name": city name if mentioned, null otherwise
- "location_type": one of "post_code", "area_name", "city_name", or "unclear"
- "needs_clarification": true if location is ambiguous or unclear, false otherwise
- "clarification_question": question to ask if needs_clarification is true, null otherwise

Example: "Find centers in Koramangala, Bangalore"
{
  "area_name": "Koramangala",
  "city_name": "Bangalore",
  "location_type": "area_name",
  "needs_clarification": false,
  "clarification_question": null
}

Example: "I'm in Olaya"
{
  "area_name": "Olaya",
  "city_name": null,
  "location_type": "area_name",
  "needs_clarification": true,
  "clarification_question": "Olaya exists in multiple cities. Which city are you looking for? Riyadh, Jeddah, or another city?"
}

Return ONLY the JSON object, no other text."""

        try:
            llm_response = await self._llm_client.chat_completion(
                messages=[{"role": "user", "content": message}],
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=200,
            )
            
            content = llm_response.get("content", "").strip()
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if json_match:
                import json
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning("llm_location_classification_failed", error=str(e))
        
        # Fallback to heuristic extraction
        return self._extract_location_info(message)

    def _calculate_distances(
        self,
        centers: List[Dict[str, Any]],
        reference_lat: Optional[float],
        reference_lon: Optional[float],
    ) -> List[Dict[str, Any]]:
        """
        Calculate distances from reference point to each center.
        Adds 'distance_km' field to each center.
        """
        if not reference_lat or not reference_lon:
            # If no reference point, return centers without distance
            for center in centers:
                center["distance_km"] = None
            return centers
        
        for center in centers:
            center_lat = center.get("latitude")
            center_lon = center.get("longitude")
            
            if center_lat and center_lon:
                distance = calculate_distance(
                    reference_lat, reference_lon,
                    center_lat, center_lon
                )
                center["distance_km"] = round(distance, 2)
            else:
                center["distance_km"] = None
        
        return centers

    def _filter_nearest_centers(
        self,
        centers: List[Dict[str, Any]],
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Filter and return top N nearest centers.
        Centers without distance are placed at the end.
        """
        # Separate centers with and without distance
        with_distance = [c for c in centers if c.get("distance_km") is not None]
        without_distance = [c for c in centers if c.get("distance_km") is None]
        
        # Sort by distance
        with_distance.sort(key=lambda x: x.get("distance_km", float('inf')))
        
        # Combine: nearest first, then centers without distance
        result = with_distance[:max_results] + without_distance[:max(0, max_results - len(with_distance))]
        
        return result[:max_results]

    async def _geocode_with_nominatim(
        self,
        query: str,
        city: Optional[str] = None,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Geocode a location using OpenStreetMap Nominatim API.
        Returns (lat, lon) or (None, None) if not found.
        """
        try:
            # Build query: "area, city, Saudi Arabia"
            search_query = query
            if city:
                search_query = f"{query}, {city}, Saudi Arabia"
            else:
                search_query = f"{query}, Saudi Arabia"

            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": search_query,
                "format": "json",
                "limit": 1,
                "countrycodes": "sa",  # Restrict to Saudi Arabia
            }
            headers = {
                "User-Agent": "SMSA-AI-Assistant/1.0",  # Required by Nominatim
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and len(data) > 0:
                            result = data[0]
                            lat = float(result.get("lat", 0))
                            lon = float(result.get("lon", 0))
                            if lat and lon:
                                logger.info(
                                    "geocoding_success",
                                    query=query,
                                    lat=lat,
                                    lon=lon,
                                )
                                return lat, lon

            logger.warning("geocoding_not_found", query=query)
            return None, None
        except Exception as e:
            logger.warning("geocoding_error", query=query, error=str(e))
            return None, None

    def _normalize_area_name(self, area_name: str) -> str:
        """
        Normalize area name for lookup: lowercase, strip, remove punctuation.
        Also extracts the first meaningful word if comma-separated.
        """
        if not area_name:
            return ""
        
        # Lowercase and strip
        normalized = area_name.lower().strip()
        
        # Remove common punctuation
        normalized = re.sub(r'[,\-\.]', ' ', normalized)
        
        # Split and take first meaningful word (ignore "nearest", "find", etc.)
        words = normalized.split()
        stop_words = {"nearest", "find", "near", "close", "to", "in", "the", "a", "an"}
        meaningful_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        if meaningful_words:
            # Try exact match first
            normalized = " ".join(meaningful_words[:2])  # Take first 2 words max
        else:
            normalized = normalized.split()[0] if normalized.split() else ""
        
        return normalized.strip()

    async def _get_user_location_coords(
        self,
        location_info: Dict[str, Any],
        city: Optional[str] = None,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Get lat/long coordinates for user's location.
        Tries multiple methods:
        1. Lookup table for common areas (with normalization and partial matching)
        2. OpenStreetMap Nominatim geocoding
        3. City center as fallback
        """
        area_name = location_info.get("area_name")
        post_code = location_info.get("post_code")
        city_name = location_info.get("city_name") or city

        # Method 1: Lookup table for common areas (with normalization)
        if area_name:
            # Normalize the area name
            normalized = self._normalize_area_name(area_name)
            
            # Try exact match first
            if normalized in self.SAUDI_AREAS:
                coords = self.SAUDI_AREAS[normalized]
                logger.info(
                    "location_from_lookup",
                    area=area_name,
                    normalized=normalized,
                    lat=coords[0],
                    lon=coords[1],
                )
                return coords
            
            # Try partial match (check if normalized starts with any key or vice versa)
            for key, coords in self.SAUDI_AREAS.items():
                # Check if normalized area contains the key or key contains normalized
                if normalized in key or key in normalized:
                    logger.info(
                        "location_from_lookup_partial",
                        area=area_name,
                        normalized=normalized,
                        matched_key=key,
                        lat=coords[0],
                        lon=coords[1],
                    )
                    return coords
            
            # Try matching first word only
            first_word = normalized.split()[0] if normalized.split() else ""
            if first_word and first_word in self.SAUDI_AREAS:
                coords = self.SAUDI_AREAS[first_word]
                logger.info(
                    "location_from_lookup_first_word",
                    area=area_name,
                    first_word=first_word,
                    lat=coords[0],
                    lon=coords[1],
                )
                return coords

        # Method 2: Try geocoding with Nominatim
        if area_name:
            lat, lon = await self._geocode_with_nominatim(area_name, city_name)
            if lat and lon:
                return lat, lon

        # Method 3: Try geocoding post code
        if post_code:
            lat, lon = await self._geocode_with_nominatim(
                f"postcode {post_code}", city_name
            )
            if lat and lon:
                return lat, lon

        # Method 4: Fallback to city center
        if city_name:
            city_lower = city_name.lower().strip()
            if city_lower in self.SAUDI_CITY_CENTERS:
                coords = self.SAUDI_CITY_CENTERS[city_lower]
                logger.info(
                    "location_from_city_center",
                    city=city_name,
                    lat=coords[0],
                    lon=coords[1],
                )
                return coords

        # No coordinates found
        logger.warning(
            "location_coords_not_found",
            area=area_name,
            post_code=post_code,
            city=city_name,
        )
        return None, None

    async def _handle_countries_query(self, message: str) -> Dict[str, Any]:
        """Handle countries query - call list_of_countries API."""
        result = await self._client.list_of_countries()
        
        if not result.get("success"):
            error_msg = result.get("error_message", "Unknown error")
            logger.error("countries_query_failed", error=error_msg)
            return {
                "agent": self.name,
                "content": "I'm having trouble accessing the countries list right now. Please try again in a moment, or contact SMSA support for assistance.",
                "centers": [],
            }
        
        countries = result.get("countries", [])
        if not countries:
            return {
                "agent": self.name,
                "content": "No countries found at this time. Please contact SMSA support for more information.",
                "centers": [],
            }
        
        content = self._format_countries_response(countries)
        return {
            "agent": self.name,
            "content": content,
            "centers": [],
        }

    async def _handle_cities_query(self, message: str, country: str) -> Dict[str, Any]:
        """Handle cities query - call list_of_cities API."""
        result = await self._client.list_of_cities(country=country)
        
        if not result.get("success"):
            error_msg = result.get("error_message", "Unknown error")
            logger.error("cities_query_failed", country=country, error=error_msg)
            country_name = "Saudi Arabia" if country == "SA" else country
            return {
                "agent": self.name,
                "content": f"I'm having trouble accessing the cities list for {country_name} right now. Please try again in a moment, or contact SMSA support for assistance.",
                "centers": [],
            }
        
        cities = result.get("cities", [])
        if not cities:
            country_name = "Saudi Arabia" if country == "SA" else country
            return {
                "agent": self.name,
                "content": f"No cities found for {country_name}. Please try a different country or contact SMSA support.",
                "centers": [],
            }
        
        content = self._format_cities_response(cities, country)
        return {
            "agent": self.name,
            "content": content,
            "centers": [],
        }

    async def _handle_retail_cities_query(self, message: str, country: str) -> Dict[str, Any]:
        """Handle retail cities query - call list_of_retail_cities API."""
        result = await self._client.list_of_retail_cities(country=country)
        
        if not result.get("success"):
            error_msg = result.get("error_message", "Unknown error")
            logger.error("retail_cities_query_failed", country=country, error=error_msg)
            country_name = "Saudi Arabia" if country == "SA" else country
            return {
                "agent": self.name,
                "content": f"I'm having trouble accessing the retail cities list for {country_name} right now. Please try again in a moment, or contact SMSA support for assistance.",
                "centers": [],
            }
        
        cities = result.get("cities", [])
        if not cities:
            country_name = "Saudi Arabia" if country == "SA" else country
            return {
                "agent": self.name,
                "content": f"No retail cities found for {country_name}. Please try a different country or contact SMSA support.",
                "centers": [],
            }
        
        content = self._format_retail_cities_response(cities, country)
        return {
            "agent": self.name,
            "content": content,
            "centers": [],
        }

    async def _handle_center_by_code_query(self, message: str, center_code: str) -> Dict[str, Any]:
        """Handle center by code query - call service_center_by_code API."""
        # Validate center code format
        if not center_code or len(center_code) < 1:
            return {
                "agent": self.name,
                "content": "I couldn't identify a valid center code. Please specify a center code (e.g., 'Show me center code RUH001').",
                "centers": [],
            }
        
        result = await self._client.service_center_by_code(center_code)
        
        if not result.get("success"):
            error_msg = result.get("error_message", "Unknown error")
            # Check if it's a "not found" error
            error_lower = error_msg.lower()
            if any(keyword in error_lower for keyword in ["not found", "invalid", "does not exist", "no center"]):
                return {
                    "agent": self.name,
                    "content": f"I couldn't find a service center with code {center_code}. Please verify the code and try again, or search for centers by location instead.",
                    "centers": [],
                }
            # Network or API errors
            return {
                "agent": self.name,
                "content": "I'm having trouble accessing the service center information right now. Please try again in a moment, or contact SMSA support for assistance.",
                "centers": [],
            }
        
        center = result.get("center")
        if not center:
            return {
                "agent": self.name,
                "content": f"No service center found with code {center_code}. Please verify the code and try again, or search for centers by location instead.",
                "centers": [],
            }
        
        content = self._format_center_by_code_response(center)
        return {
            "agent": self.name,
            "content": content,
            "centers": [center] if center else [],
        }

    async def _handle_location_based_query(
        self, message: str, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle location-based query - existing flow with geocoding and distance calculation."""
        # Step 1: Extract requested number of centers
        requested_count = self._extract_center_count(message)
        
        # Step 2: Classify location information
        location_info = await self._classify_location_with_llm(message)
        
        # Step 3: Check if clarification is needed
        if location_info.get("needs_clarification"):
            clarification_question = location_info.get("clarification_question") or \
                "I need more information about your location. Could you please specify the city or area?"
            
            return {
                "agent": self.name,
                "content": clarification_question,
                "centers": [],
                "needs_clarification": True,
                "location_info": location_info,
                "requested_count": requested_count,
            }
        
        # Step 4: Determine city
        city = location_info.get("city_name")
        if not city:
            # Try to get city from parameters or extract from message
            city = context.get("parameters", {}).get("city")
            if not city:
                # Use LLM to determine city from area/post code
                # For now, default to Riyadh if unclear
                city = "Riyadh"  # Default, could be improved with geocoding
        
        # Step 5: Get centers from API
        logger.info("retail_run_fetching_centers", city=city, location_info=location_info)
        result = await self._client.list_of_centers(city=city, country="SA")
        logger.info("retail_run_api_result", success=result.get("success"), centers_count=len(result.get("centers", [])), error=result.get("error_message"))
        
        if not result.get("success"):
            error_msg = result.get("error_message", "Unknown error")
            return {
                "agent": self.name,
                "content": f"I couldn't retrieve service centers at this time. Error: {error_msg}",
                "centers": [],
                "requested_count": requested_count,
            }

        centers = result.get("centers", [])
        
        if not centers:
            location_text = f" in {city}" if city else ""
            return {
                "agent": self.name,
                "content": f"No SMSA service centers found{location_text}. Please try a different city or contact SMSA support.",
                "centers": [],
                "requested_count": requested_count,
            }

        # Step 6: Get user location coordinates for distance calculation
        reference_lat, reference_lon = await self._get_user_location_coords(
            location_info, city=city
        )

        # Step 7: Calculate distances from user location to each center
        centers = self._calculate_distances(centers, reference_lat, reference_lon)

        # Step 8: Filter to requested number of centers (or default to 10 if more than requested)
        max_results = max(requested_count, 10)  # Get at least 10 for sorting, then limit to requested
        if reference_lat and reference_lon:
            # We have user location, filter by distance
            centers = self._filter_nearest_centers(centers, max_results=max_results)
        else:
            # No user location, just take first max_results
            centers = centers[:max_results]
        
        # Step 9: Format response using LLM
        system_prompt = """You are a helpful AI assistant for SMSA Express service centers.
Generate a friendly, clear, and informative response about SMSA service center locations.

CRITICAL: Do NOT use any thinking tags like <think>, </think>, <reasoning>, or </reasoning>. 
Respond directly to customers without showing any internal reasoning or thought process.

Guidelines:
- Show exactly the number of centers the user requested
- Include important details: address, phone, hours
- Be conversational and helpful
- If distance information is available, mention it naturally
- Format the response clearly with line breaks between centers
- Always stick to the user intent, if they ask for other things then please remind them what they have already asked
- Use plain text format, no markdown formatting
- Be concise and professional"""

        import json
        # Limit to exactly what the user requested
        limited_centers = centers[:requested_count]
        
        user_message = f"""User asked: {message}

Location information extracted:
- Type: {location_info.get('location_type', 'unclear')}
- City: {city}
- Area: {location_info.get('area_name', 'N/A')}
- Post Code: {location_info.get('post_code', 'N/A')}
- Requested count: {requested_count}

Service centers found ({len(centers)} total, showing {len(limited_centers)}):
{json.dumps(limited_centers, indent=2)}

Generate a helpful, conversational response about these service centers. 
Show exactly {requested_count} centers as the user requested.
Include address, phone, and hours for each center mentioned.

IMPORTANT: Respond directly to the customer. Do not show any thinking process, reasoning, or meta-commentary."""

        try:
            llm_response = await self._llm_client.chat_completion(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for more consistent responses
                max_tokens=600,
            )
            content = llm_response.get("content", "").strip()
            
            # Don't apply heavy reasoning cleanup for retail agent
            # Just basic cleanup if needed
            if not content:
                # Fallback to formatted response
                content = self._format_centers(centers[:10])
        except Exception as e:
            logger.warning("llm_response_failed", error=str(e))
            # Fallback to formatted response
            content = self._format_centers(centers[:10])

        return {
            "agent": self.name,
            "content": content,
            "centers": limited_centers,  # Return exactly what user requested
            "location_info": location_info,
            "city": city,
            "requested_count": requested_count,
        }

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find retail centers based on user query with geo-location intelligence.
        Routes to appropriate handler based on query intent.
        
        Args:
            context: Contains 'message', 'conversation_id', and optional 'parameters'
        
        Returns:
            Dict with 'agent', 'content', 'centers', 'needs_clarification', etc.
        """
        message: str = context.get("message", "")
        conversation_id = context.get("conversation_id", "general")
        
        logger.info(
            "retail_request",
            message=message[:100],
            conversation_id=conversation_id,
        )

        # Check if this is a conversational query (greeting, help, etc.)
        if self._is_conversational_query(message):
            logger.info("retail_conversational_request", message_preview=message[:100])
            
            # Use LLM for conversational responses
            system_prompt = """You are a helpful AI assistant for SMSA Express service centers.

CRITICAL: Do NOT use any thinking tags like <think>, </think>, <reasoning>, or </reasoning>. 
Respond directly to customers without showing any internal reasoning or thought process.

You help customers find SMSA service centers and retail locations. 
For greetings, respond warmly and explain how you can help.
For questions about services, provide helpful information.
Keep responses concise and friendly.
Use plain text format only, no markdown formatting.

Examples:
- User: "Hi" → "Hello! I'm here to help you find SMSA Express service centers. You can ask me to find centers by city, area, or post code. How can I assist you?"
- User: "What can you do?" → "I can help you locate SMSA Express service centers across Saudi Arabia and other countries. Just tell me your city, area, or post code and I'll find the nearest centers for you."
"""
            
            try:
                llm_response = await self._llm_client.chat_completion(
                    messages=[{"role": "user", "content": message}],
                    system_prompt=system_prompt,
                    temperature=0.3,  # Lower temperature for more consistent responses
                    max_tokens=200,
                )
                content = llm_response.get("content", "").strip()
                
                # Clean any reasoning content
                content = self._clean_reasoning_text(content)
                
                if not content:
                    content = "Hello! I'm here to help you find SMSA Express service centers. You can ask me to find centers by city, area, or post code. How can I assist you?"
                    
            except Exception as e:
                logger.warning("retail_conversational_response_failed", error=str(e))
                content = "Hello! I'm here to help you find SMSA Express service centers. You can ask me to find centers by city, area, or post code. How can I assist you?"
            
            return {
                "agent": self.name,
                "content": content,
                "centers": [],
                "needs_clarification": False,
                "location_info": None,
                "city": None,
            }

        try:
            # Step 1: Classify query intent
            intent_info = await self._classify_query_intent(message)
            intent_type = intent_info.get("intent_type", "location_based")
            center_code = intent_info.get("center_code")
            country = intent_info.get("country", "SA")
            
            logger.info(
                "query_intent_classified",
                intent_type=intent_type,
                center_code=center_code,
                country=country,
                conversation_id=conversation_id,
            )
            
            # Step 2: Route to appropriate handler
            if intent_type == "countries":
                return await self._handle_countries_query(message)
            elif intent_type == "cities":
                return await self._handle_cities_query(message, country)
            elif intent_type == "retail_cities":
                return await self._handle_retail_cities_query(message, country)
            elif intent_type == "center_by_code":
                if not center_code:
                    # Ambiguous query - might be center code or post code
                    # Check if it's a numeric value that could be either
                    numeric_match = re.search(r'\b(\d{1,5})\b', message)
                    if numeric_match:
                        code_value = numeric_match.group(1)
                        return {
                            "agent": self.name,
                            "content": f"I found the code '{code_value}' in your query. Could you clarify:\n- If this is a center code, please say 'center code {code_value}'\n- If this is a post code, please say 'post code {code_value}' or 'near post code {code_value}'",
                            "centers": [],
                        }
                    return {
                        "agent": self.name,
                        "content": "I couldn't identify a center code in your query. Please specify a center code (e.g., 'Show me center code RUH001') or search for centers by location.",
                        "centers": [],
                    }
                return await self._handle_center_by_code_query(message, center_code)
            else:  # location_based (default)
                result = await self._handle_location_based_query(message, context)
                logger.info(
                    "retail_response",
                    city=result.get("city"),
                    centers_count=len(result.get("centers", [])),
                    conversation_id=conversation_id,
                )
                return result

        except Exception as e:
            logger.error(
                "retail_error",
                error=str(e),
                conversation_id=conversation_id,
                exc_info=True,
            )
            return {
                "agent": self.name,
                "content": "I encountered an error while searching for service centers. Please try again or contact SMSA support.",
                "centers": [],
            }

    def _format_countries_response(self, countries: List[Dict[str, Any]]) -> str:
        """Format countries list into user-friendly text."""
        if not countries:
            return "No countries found."
        
        lines = ["Here are the countries where SMSA Express operates:\n"]
        for i, country in enumerate(countries, 1):
            country_name = country.get("name", "Unknown")
            country_code = country.get("code", "")
            is_from = country.get("is_from", False)
            
            country_line = f"{i}. {country_name}"
            if country_code:
                country_line += f" ({country_code})"
            if is_from:
                country_line += " - Available for shipping from"
            
            lines.append(country_line)
        
        return "\n".join(lines)

    def _format_cities_response(self, cities: List[Dict[str, Any]], country: str) -> str:
        """Format cities list into user-friendly text."""
        if not cities:
            return f"No cities found for country {country}."
        
        country_name = "Saudi Arabia" if country == "SA" else country
        lines = [f"Here are the cities in {country_name} where SMSA operates:\n"]
        
        for i, city in enumerate(cities, 1):
            city_name = city.get("name", "Unknown")
            is_capital = city.get("is_capital", False)
            
            city_line = f"{i}. {city_name}"
            if is_capital:
                city_line += " (Capital)"
            
            lines.append(city_line)
        
        return "\n".join(lines)

    def _format_retail_cities_response(self, cities: List[Dict[str, Any]], country: str) -> str:
        """Format retail cities list into user-friendly text."""
        if not cities:
            return f"No retail cities found for country {country}."
        
        country_name = "Saudi Arabia" if country == "SA" else country
        lines = [f"Here are the cities in {country_name} that have SMSA retail/service centers:\n"]
        
        for i, city in enumerate(cities, 1):
            city_name = city.get("name", "Unknown")
            lines.append(f"{i}. {city_name}")
        
        lines.append(f"\nYou can find retail centers in any of these cities. Would you like me to show you centers in a specific city?")
        
        return "\n".join(lines)

    def _format_center_by_code_response(self, center: Dict[str, Any]) -> str:
        """Format single center details into user-friendly text."""
        if not center:
            return "No center details found."
        
        lines = []
        
        # Center name
        center_name = center.get("name", "SMSA Service Center")
        lines.append(f"**{center_name}**\n")
        
        # Center code
        center_code = center.get("code", "N/A")
        if center_code != "N/A":
            lines.append(f"📍 Center Code: {center_code}")
        
        # Address
        address = center.get("address", "N/A")
        if address != "N/A":
            lines.append(f"📍 Address: {address}")
        
        # City, Country, Region
        city = center.get("city", "N/A")
        if city != "N/A":
            lines.append(f"🏙️ City: {city}")
        
        country = center.get("country", "N/A")
        if country != "N/A":
            lines.append(f"🌍 Country: {country}")
        
        region = center.get("region", "N/A")
        if region != "N/A":
            lines.append(f"📍 Region: {region}")
        
        # Phone
        phone = center.get("phone", "N/A")
        if phone != "N/A":
            lines.append(f"📞 Phone: {phone}")
        
        # Working hours
        working_hours = center.get("working_hours")
        if working_hours:
            hours_str = self._format_working_hours(working_hours)
            lines.append(f"🕐 Working Hours:\n{hours_str}")
        
        # Cold box
        if center.get("cold_box"):
            lines.append(f"❄️ Cold Storage Available")
        
        # Distance (if available)
        distance = center.get("distance_km")
        if distance is not None:
            lines.append(f"📏 Distance: {distance} km")
        
        # Short code
        short_code = center.get("short_code", "N/A")
        if short_code != "N/A":
            lines.append(f"🔢 Short Code: {short_code}")
        
        return "\n".join(lines)

    def _format_working_hours(self, working_hours: Dict[str, Any]) -> str:
        """Format working hours dict into readable string."""
        if not working_hours:
            return "Please call for hours"
        
        day_names = {
            "Sat": "Saturday",
            "Sun": "Sunday",
            "Mon": "Monday",
            "Tue": "Tuesday",
            "Wed": "Wednesday",
            "Thu": "Thursday",
            "Fri": "Friday",
        }
        
        hours_list = []
        for day_short, day_full in day_names.items():
            shifts = working_hours.get(day_short, [])
            if shifts:
                hours_list.append(f"{day_full}: {', '.join(shifts)}")
            else:
                hours_list.append(f"{day_full}: Closed")
        
        return "; ".join(hours_list)

    def _format_centers(self, centers: List[Dict[str, Any]]) -> str:
        """Format centers list into user-friendly text."""
        if not centers:
            return "No service centers found for the specified location."

        lines: List[str] = []
        for i, center in enumerate(centers[:10], 1):  # Top 10 only
            center_lines = [f"{i}. {center.get('name', 'SMSA Service Center')}"]
            
            if center.get("address") and center.get("address") != "N/A":
                center_lines.append(f"   📍 Address: {center['address']}")
            
            if center.get("city") and center.get("city") != "N/A":
                center_lines.append(f"   🏙️ City: {center['city']}")
            
            if center.get("distance_km") is not None:
                center_lines.append(f"   📏 Distance: {center['distance_km']} km")
            
            if center.get("phone") and center.get("phone") != "N/A":
                center_lines.append(f"   📞 Phone: {center['phone']}")
            
            # Format working hours
            working_hours = center.get("working_hours")
            if working_hours:
                hours_str = self._format_working_hours(working_hours)
                center_lines.append(f"   🕐 Hours: {hours_str}")
            elif center.get("hours") and center.get("hours") != "N/A":
                center_lines.append(f"   🕐 Hours: {center['hours']}")
            
            # Add ColdBox info if available
            if center.get("cold_box"):
                center_lines.append(f"   ❄️ Cold Storage Available")
            
            lines.append("\n".join(center_lines))

        return "\n\n".join(lines)