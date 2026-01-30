"""
LLM Client for Qwen text model integration.

Handles chat completions, intent classification, and text generation
using the self-hosted Qwen3-32B model via Huawei Cloud ModelArts.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

from ..config.settings import get_settings

settings = get_settings()


class LLMClient:
    """
    Client for interacting with Qwen text model via Huawei Cloud ModelArts.

    Supports:
    - Chat completions (streaming and non-streaming)
    - Intent classification
    - FAQ response generation
    - General text generation
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize LLM client.

        Args:
            api_url: ModelArts API endpoint (defaults to settings)
            model: Model name (defaults to settings)
            api_key: API key (defaults to settings)
        """
        self.api_url = api_url or settings.llm_text_api_url
        self.model = model or settings.llm_text_model
        self.api_key = api_key or settings.llm_api_key
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any] | AsyncIterator[Dict[str, Any]]:
        """
        Send a chat completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            system_prompt: Optional system prompt to prepend

        Returns:
            Dict with 'content' and 'usage' if not streaming,
            AsyncIterator of token dicts if streaming
        """
        session = await self._get_session()

        # Prepend system prompt if provided
        payload_messages = messages.copy()
        if system_prompt:
            payload_messages.insert(0, {"role": "system", "content": system_prompt})

        payload = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        if stream:
            return self._stream_completion(session, payload, headers)
        else:
            return await self._non_stream_completion(session, payload, headers)

    async def _non_stream_completion(
        self,
        session: aiohttp.ClientSession,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Handle non-streaming completion."""
        async with session.post(
            self.api_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            response.raise_for_status()
            data = await response.json()

            # Extract content from response
            content = ""
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")

            usage = data.get("usage", {})

            return {
                "content": content,
                "usage": usage,
                "model": data.get("model", self.model),
            }

    async def _stream_completion(
        self,
        session: aiohttp.ClientSession,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Handle streaming completion."""
        async with session.post(
            self.api_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
        ) as response:
            response.raise_for_status()

            async for line in response.content:
                if not line:
                    continue

                line_str = line.decode("utf-8").strip()
                if not line_str or not line_str.startswith("data:"):
                    continue

                # Parse SSE format: "data: {...}"
                json_str = line_str[5:].strip()
                if json_str == "[DONE]":
                    break

                try:
                    data = json.loads(json_str)
                    if "choices" in data and len(data["choices"]) > 0:
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield {
                                "content": content,
                                "finish_reason": data["choices"][0].get("finish_reason"),
                            }
                except json.JSONDecodeError:
                    continue

    async def classify_intent(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Classify user intent using LLM.

        Args:
            message: User's message
            conversation_history: Previous messages for context

        Returns:
            Dict with 'intent', 'confidence', 'parameters'
        """
        system_prompt = """You are an intent classifier for SMSA Express AI Assistant.
Classify the user's message into one of these intents:
- TRACKING: Shipment tracking queries (e.g., "track AWB 123", "where is my package")
- RATES: Shipping rate inquiries (e.g., "how much to ship", "rate from Riyadh to Jeddah")
- LOCATIONS: Service center/branch location queries (e.g., "nearest branch", "Riyadh office")
- FAQ: General questions (e.g., "what is your return policy", "how do I schedule pickup")
- GENERAL: Other queries

Respond with JSON only:
{
  "intent": "TRACKING|RATES|LOCATIONS|FAQ|GENERAL",
  "confidence": 0.0-1.0,
  "parameters": {}
}"""

        messages = []
        if conversation_history:
            messages.extend(conversation_history[-5:])  # Last 5 messages for context
        messages.append({"role": "user", "content": message})

        try:
            response = await self.chat_completion(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.0,  # Deterministic for classification
                max_tokens=200,
            )

            # Parse JSON response
            content = response.get("content", "").strip()
            # Remove markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            result = json.loads(content)
            return {
                "intent": result.get("intent", "GENERAL"),
                "confidence": float(result.get("confidence", 0.5)),
                "parameters": result.get("parameters", {}),
            }
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Fallback to keyword-based classification
            return {
                "intent": "GENERAL",
                "confidence": 0.0,
                "parameters": {},
                "error": str(e),
            }

    async def generate_response(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a response using the LLM.

        Args:
            prompt: User prompt or question
            context: Additional context (conversation history, retrieved docs, etc.)
            system_prompt: System instructions
            temperature: Sampling temperature

        Returns:
            Generated text response
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if context:
            context_str = json.dumps(context, indent=2)
            messages.append(
                {
                    "role": "user",
                    "content": f"Context:\n{context_str}\n\nUser Question: {prompt}",
                }
            )
        else:
            messages.append({"role": "user", "content": prompt})

        response = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=2000,
        )

        return response.get("content", "")
