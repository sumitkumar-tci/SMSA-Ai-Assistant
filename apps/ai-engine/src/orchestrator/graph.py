"""
LangGraph workflow definition for the AI orchestrator.

This defines the state machine that orchestrates intent classification,
context assembly, agent routing, and response generation.
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .intent_classifier import Intent, IntentClassifier
from .state import OrchestratorState
from ..agents.faq import FAQAgent
from ..agents.rates import RatesAgent
from ..agents.retail import RetailCentersAgent
from ..agents.tracking import TrackingAgent


class OrchestratorGraph:
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
        self._classifier = IntentClassifier()
        self._tracking_agent = TrackingAgent()
        self._rates_agent = RatesAgent()
        self._retail_agent = RetailCentersAgent()
        self._faq_agent = FAQAgent()

        # Build the graph
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(OrchestratorState)

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

    async def _classify_intent_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Classify user intent from the message.

        Priority:
        1. Explicit selected_agent from frontend
        2. Explicit intent from request
        3. Auto-classification via IntentClassifier
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

        # Priority 3: Auto-classify
        intent = self._classifier.classify(state.message)
        parameters = self._classifier.extract_parameters(state.message)

        return {
            "intent": intent,
            "intent_confidence": 0.8,  # Keyword-based has lower confidence
            "parameters": parameters,
        }

    async def _assemble_context_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Assemble context from conversation history, files, and semantic search.

        TODO: Wire in MongoDB and Vector DB once credentials are available.
        For now, this is a placeholder that returns empty context.
        """
        # TODO: Load conversation history from MongoDB
        # conversation_history = await db_client.get_conversation_history(
        #     state.conversation_id, limit=10
        # )

        # TODO: Load file context from OBS/storage
        # file_context = await storage_client.get_file_context(
        #     state.conversation_id
        # )

        # TODO: Semantic search for FAQ/RAG
        # if state.intent == Intent.FAQ:
        #     semantic_context = await vector_db.search_similar(
        #         state.message, top_k=5
        #     )

        return {
            "conversation_history": [],  # Placeholder
            "file_context": {},  # Placeholder
            "semantic_context": {},  # Placeholder
        }

    async def _route_to_agent_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Route to the appropriate specialized agent based on intent.
        """
        context: Dict[str, Any] = {
            "conversation_id": state.conversation_id,
            "user_id": state.user_id,
            "message": state.message,
            "intent": state.intent,
            "parameters": state.parameters,
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

    async def _aggregate_response_node(self, state: OrchestratorState) -> Dict[str, Any]:
        """
        Aggregate and format the final response.

        Extracts content and metadata from agent response.
        """
        content = ""
        metadata: Dict[str, Any] = {}

        if state.agent_response:
            content = state.agent_response.get("content", "")
            metadata = {
                "agent": state.agent_response.get("agent", state.agent_name),
                **state.agent_response.get("metadata", {}),
            }

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
        # Convert dict to OrchestratorState
        state = OrchestratorState(**initial_state)

        # Run the graph
        # Note: LangGraph's ainvoke returns a dict, not the Pydantic model
        final_state = await self._graph.ainvoke(state)

        return final_state
