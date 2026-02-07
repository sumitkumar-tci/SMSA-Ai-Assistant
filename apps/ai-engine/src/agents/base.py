from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, AsyncIterator, Dict


class SMSAAIAssistantBaseAgent(ABC):
    """
    Abstract base class for all agents.

    Each specialized agent:
    - Defines a `name`
    - Provides a `system_prompt` loaded from the prompts directory (optional)
    - Implements `run()` which receives the orchestration context
    - Optionally implements `run_stream()` for streaming responses
    """

    name: str
    system_prompt: str | None = None

    def __init__(self) -> None:
        # Attempt to load a system prompt matching the agent name, if present.
        prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
        candidate = prompts_dir / f"{self.name}_agent_prompt.txt"
        if candidate.is_file():
            try:
                self.system_prompt = candidate.read_text(encoding="utf-8")
            except OSError:
                self.system_prompt = None

    @abstractmethod
    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the agent with the given context and return a structured dict."""
        raise NotImplementedError

    async def run_stream(self, context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """
        Execute the agent with streaming support.
        
        Default implementation falls back to non-streaming run().
        Agents can override this for true streaming.
        
        Yields:
            Dict chunks with 'type', 'content', 'metadata'
        """
        # Default: call run() and yield the full response
        result = await self.run(context)
        yield {
            "type": "token",
            "content": result.get("content", ""),
            "metadata": {k: v for k, v in result.items() if k != "content"},
        }

