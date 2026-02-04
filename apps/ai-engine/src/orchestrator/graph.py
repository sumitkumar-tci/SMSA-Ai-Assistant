"""
LangGraph workflow definition for the AI orchestrator.

This defines the state machine that orchestrates intent classification,
context assembly, agent routing, and response generation.
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .intent_classifier import Intent, SMSAAIAssistantIntentClassifier
from .state import SMSAAIAssistantOrchestratorState
from ..agents.faq import SMSAAIAssistantFAQAgent
from ..agents.rates import SMSAAIAssistantRatesAgent
from ..agents.retail import SMSAAIAssistantRetailCentersAgent
from ..agents.tracking import SMSAAIAssistantTrackingAgent
from ..services.storage import SMSAAIAssistantStorageClient
from ..services.vision_client import SMSAAIAssistantVisionClient
from ..services.db import SMSAAIAssistantDatabaseManager
from ..logging_config import logger


class SMSAAIAssistantOrchestratorGraph:
    """
    LangGraph-based orchestrator workflow.

    Workflow:
    1. classify_intent -> Classify user intent
    2. assemble_context -> Load conversation history, files, semantic context
    3. route_to_agent -> Route to appropriate specialized agent
    4. aggregate_response -> Format and return response
    """

    def __init__(self) -> None:
        """Initialize the orchestrator graph."""
        self._classifier = SMSAAIAssistantIntentClassifier()
        self._tracking_agent = SMSAAIAssistantTrackingAgent()
        self._rates_agent = SMSAAIAssistantRatesAgent()
        self._retail_agent = SMSAAIAssistantRetailCentersAgent()
        self._faq_agent = SMSAAIAssistantFAQAgent()
        self._storage_client = SMSAAIAssistantStorageClient()
        self._vision_client = SMSAAIAssistantVisionClient()
        self._db_manager = SMSAAIAssistantDatabaseManager()

        # Build the graph
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(SMSAAIAssistantOrchestratorState)

        # Add nodes
        workflow.add_node("classify_intent", self._classify_intent_node)
        workflow.add_node("assemble_context", self._assemble_context_node)
        workflow.add_node("route_to_agent", self._route_to_agent_node)
        workflow.add_node("aggregate_response", self._aggregate_response_node)

        # Define edges
        workflow.set_entry_point("classify_intent")
        workflow.add_edge("classify_intent", "assemble_context")
        workflow.add_edge("assemble_context", "route_to_agent")
        workflow.add_edge("route_to_agent", "aggregate_response")
        workflow.add_edge("aggregate_response", END)

        return workflow.compile()

    async def _classify_intent_node(self, state: SMSAAIAssistantOrchestratorState) -> Dict[str, Any]:
        """
        Classify user intent from the message.

        Priority:
        1. Explicit selected_agent from frontend
        2. Explicit intent from request
        3. Auto-classification via SMSAAIAssistantIntentClassifier
        """
        # Priority 1: Explicit agent selection
        if state.selected_agent:
            agent_to_intent = {
                "tracking": Intent.TRACKING,
                "rates": Intent.RATES,
                "retail": Intent.LOCATIONS,
                "faq": Intent.FAQ,
            }
            intent = agent_to_intent.get(state.selected_agent, Intent.GENERAL)
            return {
                "intent": intent,
                "intent_confidence": 1.0,
            }

        # Priority 2: Explicit intent
        if state.explicit_intent:
            return {
                "intent": state.explicit_intent,
                "intent_confidence": 1.0,
            }

        # Priority 3: Auto-classify (keyword-based, with optional LLM fallback)
        # Use LLM if keyword classification is ambiguous
        intent, confidence = await self._classifier.classify_async(
            state.message, use_llm_for_ambiguous=True
        )
        parameters = self._classifier.extract_parameters(state.message)

        return {
            "intent": intent,
            "intent_confidence": confidence,
            "parameters": parameters,
        }

    async def _assemble_context_node(self, state: SMSAAIAssistantOrchestratorState) -> Dict[str, Any]:
        """
        Assemble context from conversation history, files, and semantic search.

        Loads file context from OBS if file_id is provided.
        Processes images with Vision API to extract AWB/shipment details.
        
        Note: File uploads are only supported for tracking agent.
        """
        file_context: Dict[str, Any] = {}

        # Load file context if file_id is provided AND agent is tracking
        # File uploads are only for tracking agent (waybill images)
        if state.file_id and state.intent == Intent.TRACKING:
            try:
                # Try to get conversation context from OBS (may contain file metadata)
                context_data = await self._storage_client.get_conversation_context(
                    state.conversation_id
                )
                if context_data and "files" in context_data:
                    file_context = context_data["files"].get(state.file_id, {})
                
                # If file is an image and we have file_url, process it
                if state.file_url and not file_context.get("extracted_data"):
                    # Check if it's an image (simple check - could be enhanced)
                    if any(ext in state.file_url.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                        try:
                            logger.info("processing_file_with_vision", file_id=state.file_id)
                            # Download file from OBS (we'd need to implement this or use file_url)
                            # For now, if we have extracted_data from upload, it should be in context
                            # This is a placeholder - in production, we'd download and process
                            pass
                        except Exception as e:
                            logger.warning("vision_processing_skipped", error=str(e))
            except Exception as e:
                logger.warning("file_context_load_failed", error=str(e), file_id=state.file_id)

        # Load conversation history from MongoDB
        conversation_history = []
        try:
            if state.conversation_id and state.conversation_id != "default":
                conversation_history = await self._db_manager.get_conversation_history(
                    state.conversation_id, limit=10
                )
                logger.info(
                    "conversation_history_loaded",
                    conversation_id=state.conversation_id,
                    message_count=len(conversation_history),
                )
        except Exception as e:
            # If MongoDB connection fails, log warning but continue without history
            logger.warning(
                "conversation_history_load_failed",
                error=str(e),
                conversation_id=state.conversation_id,
            )
            conversation_history = []

        # TODO: Semantic search for FAQ/RAG
        # if state.intent == Intent.FAQ:
        #     semantic_context = await vector_db.search_similar(
        #         state.message, top_k=5
        #     )

        return {
            "conversation_history": conversation_history,
            "file_context": file_context,
            "semantic_context": {},  # Placeholder
        }

    async def _route_to_agent_node(self, state: SMSAAIAssistantOrchestratorState) -> Dict[str, Any]:
        """
        Route to the appropriate specialized agent based on intent.
        """
        # Extract AWB from file context if available (for tracking agent)
        parameters = state.parameters.copy()
        if state.file_context:
            extracted_data = state.file_context.get("extracted_data", {})
            if extracted_data and extracted_data.get("awb"):
                # Add AWB from file to parameters
                parameters["awb"] = extracted_data["awb"]
                # Also add other extracted fields
                if extracted_data.get("origin"):
                    parameters["origin_city"] = extracted_data["origin"]
                if extracted_data.get("destination"):
                    parameters["destination_city"] = extracted_data["destination"]
                if extracted_data.get("weight"):
                    parameters["weight"] = extracted_data["weight"]
                if extracted_data.get("pieces"):
                    parameters["pieces"] = extracted_data["pieces"]

        context: Dict[str, Any] = {
            "conversation_id": state.conversation_id,
            "user_id": state.user_id,
            "message": state.message,
            "intent": state.intent,
            "parameters": parameters,
            "conversation_history": state.conversation_history,
            "file_context": state.file_context,
            "semantic_context": state.semantic_context,
        }

        agent_name = "system"
        agent_response: Dict[str, Any] = {}

        if state.intent == Intent.TRACKING:
            agent_name = "tracking"
            agent_response = await self._tracking_agent.run(context)
        elif state.intent == Intent.RATES:
            agent_name = "rates"
            agent_response = await self._rates_agent.run(context)
        elif state.intent == Intent.LOCATIONS:
            agent_name = "retail"
            agent_response = await self._retail_agent.run(context)
        elif state.intent == Intent.FAQ:
            agent_name = "faq"
            agent_response = await self._faq_agent.run(context)
        else:
            # GENERAL / AMBIGUOUS
            agent_response = {
                "agent": "system",
                "content": "I can help with tracking, rates, service centers, and FAQs. Please select an agent or specify what you need.",
            }

        return {
            "agent_name": agent_name,
            "agent_response": agent_response,
        }

    async def _aggregate_response_node(self, state: SMSAAIAssistantOrchestratorState) -> Dict[str, Any]:
        """
        Aggregate and format the final response.

        Extracts content and metadata from agent response.
        Preserves structured data (like tracking events) for frontend rendering.
        Saves conversation to MongoDB.
        """
        content = ""
        metadata: Dict[str, Any] = {}

        if state.agent_response:
            content = state.agent_response.get("content", "")
            metadata = {
                "agent": state.agent_response.get("agent", state.agent_name),
                **state.agent_response.get("metadata", {}),
            }
            
            # Preserve structured data from agent response (e.g., tracking events, raw_data)
            # This allows frontend to render rich UI components
            if "type" in state.agent_response:
                metadata["type"] = state.agent_response["type"]
            if "raw_data" in state.agent_response:
                metadata["raw_data"] = state.agent_response["raw_data"]
            if "events" in state.agent_response:
                metadata["events"] = state.agent_response["events"]
            if "current_status" in state.agent_response:
                metadata["current_status"] = state.agent_response["current_status"]
            if "status_explanation" in state.agent_response:
                metadata["status_explanation"] = state.agent_response["status_explanation"]
            if "requires_awb" in state.agent_response:
                metadata["requires_awb"] = state.agent_response["requires_awb"]
            # Retail centers data
            if "centers" in state.agent_response:
                metadata["centers"] = state.agent_response["centers"]
            if "location_info" in state.agent_response:
                metadata["location_info"] = state.agent_response["location_info"]
            if "city" in state.agent_response:
                metadata["city"] = state.agent_response["city"]
            if "needs_clarification" in state.agent_response:
                metadata["needs_clarification"] = state.agent_response["needs_clarification"]

        # Save conversation to MongoDB
        try:
            if state.conversation_id and state.conversation_id != "default":
                user_id = state.user_id or "anonymous"
                
                # Ensure conversation exists (create if it doesn't)
                try:
                    await self._db_manager.ensure_conversation_exists(
                        conversation_id=state.conversation_id,
                        user_id=user_id,
                        metadata={
                            "intent": state.intent.value if state.intent else None,
                            "selected_agent": state.selected_agent,
                        },
                    )
                except Exception as conv_error:
                    logger.warning("conversation_ensure_failed", error=str(conv_error))
                    # Continue - messages can still be saved even if conversation record doesn't exist

                # Save user message
                try:
                    await self._db_manager.save_message(
                        conversation_id=state.conversation_id,
                        role="user",
                        content=state.message,
                        metadata={
                            "intent": state.intent.value if state.intent else None,
                            "intent_confidence": state.intent_confidence,
                            "selected_agent": state.selected_agent,
                        },
                    )
                    logger.debug("user_message_saved", conversation_id=state.conversation_id)
                except Exception as msg_error:
                    logger.warning("user_message_save_failed", error=str(msg_error))

                # Save assistant response
                try:
                    await self._db_manager.save_message(
                        conversation_id=state.conversation_id,
                        role="assistant",
                        content=content,
                        metadata={
                            "agent": metadata.get("agent", state.agent_name),
                            "intent": state.intent.value if state.intent else None,
                        },
                    )
                    logger.debug("assistant_message_saved", conversation_id=state.conversation_id)
                except Exception as resp_error:
                    logger.warning("assistant_message_save_failed", error=str(resp_error))
        except Exception as db_error:
            # If MongoDB is unavailable, log warning but continue
            logger.warning(
                "mongodb_save_failed",
                error=str(db_error),
                conversation_id=state.conversation_id,
            )

        return {
            "content": content,
            "metadata": metadata,
        }

    async def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the orchestrator workflow.

        Args:
            initial_state: Initial state dict with message, conversation_id, etc.

        Returns:
            Final state dict with response content and metadata
        """
        # Convert dict to SMSAAIAssistantOrchestratorState
        state = SMSAAIAssistantOrchestratorState(**initial_state)

        # Run the graph
        # Note: LangGraph's ainvoke returns a dict, not the Pydantic model
        final_state = await self._graph.ainvoke(state)

        return final_state
