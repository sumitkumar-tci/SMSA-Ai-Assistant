from __future__ import annotations

from typing import Any, Dict

from .base import BaseAgent


class FAQAgent(BaseAgent):
    """
    Placeholder agent for FAQ / knowledge-base questions using RAG.

    Future responsibilities:
    - Use Deepseek embeddings to vectorize the query
    - Query Qdrant for relevant documents
    - Generate grounded answers using the LLM and response templates
    """

    name = "faq"

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "agent": self.name,
            "content": "FAQ agent is not implemented yet. I can only handle tracking queries for now.",
        }


