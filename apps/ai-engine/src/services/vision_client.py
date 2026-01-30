"""
Vision Client for Qwen-VL model integration.

Handles image analysis, OCR, and document extraction using the
Qwen3-VL-32B-Instruct vision-language model via Huawei Cloud ModelArts.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from ..config.settings import get_settings

settings = get_settings()


class VisionClient:
    """
    Client for interacting with Qwen-VL vision model via Huawei Cloud ModelArts.

    Supports:
    - Image analysis and OCR
    - SAWB document extraction
    - Multi-modal understanding (text + images)
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize Vision client.

        Args:
            api_url: ModelArts API endpoint (defaults to settings)
            model: Vision model name (defaults to settings)
            api_key: API key (defaults to settings)
        """
        self.api_url = api_url or settings.llm_vision_api_url
        self.model = model or settings.llm_vision_model
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

    @staticmethod
    def _encode_image_to_base64(image_path: str | Path) -> str:
        """
        Encode image file to base64.

        Args:
            image_path: Path to image file

        Returns:
            Base64-encoded image string
        """
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def _encode_image_bytes_to_base64(image_bytes: bytes) -> str:
        """
        Encode image bytes to base64.

        Args:
            image_bytes: Image bytes

        Returns:
            Base64-encoded image string
        """
        return base64.b64encode(image_bytes).decode("utf-8")

    async def analyze_image(
        self,
        image_path: str | Path | bytes,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """
        Analyze an image with a text prompt.

        Args:
            image_path: Path to image file or image bytes
            prompt: Text prompt/question about the image
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Dict with 'content' (analysis result) and 'usage'
        """
        session = await self._get_session()

        # Encode image
        if isinstance(image_path, bytes):
            img_b64 = self._encode_image_bytes_to_base64(image_path)
            mime_type = "image/png"  # Default, could be detected
        else:
            img_b64 = self._encode_image_to_base64(image_path)
            # Detect MIME type from extension
            path = Path(image_path)
            ext = path.suffix.lower()
            mime_type_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime_type = mime_type_map.get(ext, "image/png")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{img_b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        async with session.post(
            self.api_url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
        ) as response:
            response.raise_for_status()
            data = await response.json()

            content = ""
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")

            return {
                "content": content,
                "usage": data.get("usage", {}),
                "model": data.get("model", self.model),
            }

    async def extract_awb_from_image(
        self, image_path: str | Path | bytes
    ) -> Dict[str, Any]:
        """
        Extract AWB number and shipment details from SAWB document image.

        Args:
            image_path: Path to SAWB image or image bytes

        Returns:
            Dict with 'awb', 'origin', 'destination', 'weight', etc.
        """
        prompt = """Extract the following information from this shipping waybill (SAWB) document:
1. AWB number (Air Waybill number)
2. Origin city/country
3. Destination city/country
4. Weight (if visible)
5. Number of pieces (if visible)
6. Shipper name (if visible)
7. Consignee name (if visible)

Respond with JSON only:
{
  "awb": "AWB number or null",
  "origin": "Origin city or null",
  "destination": "Destination city or null",
  "weight": "Weight in kg or null",
  "pieces": "Number of pieces or null",
  "shipper": "Shipper name or null",
  "consignee": "Consignee name or null"
}"""

        result = await self.analyze_image(
            image_path=image_path,
            prompt=prompt,
            max_tokens=500,
            temperature=0.1,  # Low temperature for structured extraction
        )

        # Parse JSON from response
        content = result.get("content", "").strip()
        # Remove markdown code blocks if present
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            extracted_data = json.loads(content)
            return {
                **extracted_data,
                "raw_response": result.get("content", ""),
            }
        except json.JSONDecodeError:
            # Fallback: return raw content
            return {
                "awb": None,
                "origin": None,
                "destination": None,
                "weight": None,
                "pieces": None,
                "shipper": None,
                "consignee": None,
                "raw_response": content,
                "error": "Failed to parse JSON from vision model",
            }

    async def ocr_text_from_image(
        self, image_path: str | Path | bytes
    ) -> str:
        """
        Extract all text from an image using OCR.

        Args:
            image_path: Path to image or image bytes

        Returns:
            Extracted text content
        """
        prompt = "Read the text in this image and tell me exactly what it says. Preserve the formatting and structure."

        result = await self.analyze_image(
            image_path=image_path,
            prompt=prompt,
            max_tokens=2000,
            temperature=0.2,
        )

        return result.get("content", "")
