from __future__ import annotations

from typing import Any, Dict

from ..logging_config import logger
from ..services.llm_client import SMSAAIAssistantLLMClient
from ..services.faq_data import get_faq_data_loader
from .base import SMSAAIAssistantBaseAgent


class SMSAAIAssistantFAQAgent(SMSAAIAssistantBaseAgent):
    """
    FAQ agent that answers questions about SMSA services using Qwen LLM.

    Uses LLM to generate contextual responses based on user questions.
    Future: Will integrate with RAG/vector DB for more accurate, grounded answers.
    """

    name = "faq"

    def __init__(self) -> None:
        super().__init__()
        self._llm_client = SMSAAIAssistantLLMClient()
        self._faq_data_loader = get_faq_data_loader()

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Answer FAQ questions using LLM.

        Args:
            context: Contains 'message' (user question) and optional 'conversation_history'

        Returns:
            Dict with 'agent', 'content', and optional metadata
        """
        message: str = context.get("message", "")
        conversation_history = context.get("conversation_history", [])

        if not message.strip():
            return {
                "agent": self.name,
                "content": "Please ask me a question about SMSA services, policies, or shipping.",
            }

        logger.info(
            "faq_request",
            message=message[:100],
            conversation_id=context.get("conversation_id"),
        )

        # Get relevant FAQ context
        faq_context = self._faq_data_loader.get_context_for_llm(message, max_chunks=3)
        
        # System prompt for FAQ responses
        system_prompt = """You are a helpful AI assistant for SMSA Express.

Answer questions about SMSA services concisely (2-4 sentences max).
Use the provided context to answer accurately.
If context doesn't have the answer, say so briefly.
For tracking/rates/locations, suggest the appropriate agent.
Be direct and helpful - avoid long explanations."""
        
        # Add FAQ context to system prompt if available
        if faq_context:
            system_prompt += f"\n\nRelevant SMSA Information:\n{faq_context}"

        try:
            # Prepare conversation history for context
            llm_messages = []
            if conversation_history:
                # Convert conversation history to LLM format
                for msg in conversation_history[-5:]:  # Last 5 messages
                    role = msg.get("role", "user")
                    content = msg.get("content", msg.get("message", ""))
                    if content:
                        llm_messages.append({"role": role, "content": content})

            llm_messages.append({"role": "user", "content": message})

            # Generate response using LLM
            response = await self._llm_client.chat_completion(
                messages=llm_messages,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=300,  # Shorter responses
            )

            content = response.get("content", "").strip()

            if not content:
                content = "I apologize, but I couldn't generate a response. Please try rephrasing your question."

            logger.info(
                "faq_response",
                message_len=len(message),
                response_len=len(content),
                conversation_id=context.get("conversation_id"),
            )

            return {
                "agent": self.name,
                "content": content,
                "metadata": {
                    "model": response.get("model"),
                    "usage": response.get("usage", {}),
                },
            }

        except Exception as e:
            logger.error(
                "faq_error",
                error=str(e),
                conversation_id=context.get("conversation_id"),
                exc_info=True,
            )
            return {
                "agent": self.name,
                "content": "I encountered an error while processing your question. Please try again or contact SMSA support for assistance.",
                "metadata": {"error": str(e)},
            }


