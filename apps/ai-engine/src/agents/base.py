from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Each specialized agent:
    - Defines a `name`
    - Provides a `system_prompt` loaded from the prompts directory (optional)
    - Implements `run()` which receives the orchestration context
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


