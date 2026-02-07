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

    async def run_stream(self, context: Dict[str, Any]):
        """Execute FAQ agent with streaming support."""
        # Reset thinking state for new request
        self._inside_thinking = False
        
        message: str = context.get("message", "")
        conversation_history = context.get("conversation_history", [])

        if not message.strip():
            yield {
                "type": "token",
                "content": "Please ask me a question about SMSA services, policies, or shipping.",
                "metadata": {"agent": self.name},
            }
            return

        logger.info(
            "faq_request",
            message=message[:100],
            conversation_id=context.get("conversation_id"),
        )

        # Get relevant FAQ context
        faq_context = self._faq_data_loader.get_context_for_llm(message, max_chunks=3)
        
        # System prompt for FAQ responses
        system_prompt = """You are a helpful AI assistant for SMSA Express.

CRITICAL: Do NOT use any thinking tags like <think>, </think>, <reasoning>, or </reasoning>. Respond directly to customers without showing any internal reasoning or thought process.

Answer questions about SMSA services concisely (2-4 sentences max).
Use the provided context to answer accurately.
If context doesn't have the answer, say so briefly.
For tracking/rates/locations, suggest the appropriate agent.
Be direct and helpful - avoid long explanations.
Use plain text format only, no markdown formatting."""
        
        # Add FAQ context to system prompt if available
        if faq_context:
            system_prompt += f"\n\nRelevant SMSA Information:\n{faq_context}"

        try:
            # Prepare conversation history for context
            llm_messages = []
            if conversation_history:
                for msg in conversation_history[-5:]:
                    role = msg.get("role", "user")
                    content = msg.get("content", msg.get("message", ""))
                    if content:
                        llm_messages.append({"role": role, "content": content})

            llm_messages.append({"role": "user", "content": message})

            # Stream LLM response
            chunk_count = 0
            async for chunk in self._llm_client.chat_completion_stream(
                messages=llm_messages,
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for more consistent responses
                max_tokens=300,
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
                
                if content:
                    yield {
                        "type": "token",
                        "content": content,
                        "metadata": {"agent": self.name},
                    }

        except Exception as e:
            logger.error("faq_stream_error", error=str(e), exc_info=True)
            yield {
                "type": "token",
                "content": "I encountered an error while processing your question. Please try again or contact SMSA support for assistance.",
                "metadata": {"agent": self.name, "error": str(e)},
            }

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

CRITICAL: Do NOT use any thinking tags like <think>, </think>, <reasoning>, or </reasoning>. Respond directly to customers without showing any internal reasoning or thought process.

Answer questions about SMSA services concisely (2-4 sentences max).
Use the provided context to answer accurately.
If context doesn't have the answer, say so briefly.
For tracking/rates/locations, suggest the appropriate agent.
Be direct and helpful - avoid long explanations.
Use plain text format only, no markdown formatting."""
        
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
                temperature=0.3,  # Lower temperature for more consistent responses
                max_tokens=300,  # Shorter responses
            )

            content = response.get("content", "").strip()
            
            # Clean any reasoning content
            content = self._clean_reasoning_text(content)

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


