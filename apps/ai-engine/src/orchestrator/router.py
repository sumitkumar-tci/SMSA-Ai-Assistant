"""
Orchestrator router with LangGraph integration.

This module provides both the new LangGraph-based orchestrator and
a backwards-compatible wrapper for the existing FastAPI route.
"""

from __future__ import annotations

from typing import Any, Dict

from .graph import SMSAAIAssistantOrchestratorGraph

# Initialize the LangGraph orchestrator
_orchestrator_graph = SMSAAIAssistantOrchestratorGraph()


async def route_message(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route a message through the LangGraph orchestrator.

    This is the main entrypoint used by the FastAPI route.
    It converts the context dict to SMSAAIAssistantOrchestratorState, runs the graph,
    and returns a compatible response dict.

    Args:
        context: Request context with message, conversation_id, etc.

    Returns:
        Dict with 'agent', 'content', and optional 'metadata'
    """
    # Convert context to SMSAAIAssistantOrchestratorState format
    initial_state = {
        "message": context.get("message", ""),
        "conversation_id": context.get("conversation_id", "default"),
        "user_id": context.get("user_id"),
        "selected_agent": context.get("selected_agent"),
        "explicit_intent": context.get("explicit_intent"),
        "file_id": context.get("file_id"),
        "file_url": context.get("file_url"),
    }

    # Run the LangGraph workflow
    # Note: LangGraph returns a dict, not the Pydantic model
    final_state: Dict[str, Any] = await _orchestrator_graph.run(initial_state)

    # Convert back to dict format for compatibility
    metadata = final_state.get("metadata", {})
    agent_name = final_state.get("agent_name")
    
    return {
        "agent": metadata.get("agent", agent_name or "system"),
        "content": final_state.get("content", ""),
        "metadata": metadata,
    }

