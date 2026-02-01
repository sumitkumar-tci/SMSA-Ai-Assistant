"""
LangGraph state model for the AI orchestrator.

This defines the state that flows through the LangGraph workflow,
enabling stateful conversation management and context assembly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .intent_classifier import Intent


class SMSAAIAssistantOrchestratorState(BaseModel):
    """
    State model for the LangGraph orchestrator workflow.

    This state is passed between nodes in the graph, allowing each node
    to read and update relevant fields.
    """

    # Input
    message: str = Field(..., description="User's input message")
    conversation_id: str = Field(..., description="Unique conversation identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    selected_agent: Optional[str] = Field(
        None, description="Explicitly selected agent from frontend"
    )
    explicit_intent: Optional[Intent] = Field(
        None, description="Explicit intent if provided in request"
    )
    file_id: Optional[str] = Field(None, description="OBS object key for uploaded file")
    file_url: Optional[str] = Field(None, description="Direct file URL")

    # Classification
    intent: Optional[Intent] = Field(
        None, description="Classified intent from message"
    )
    intent_confidence: float = Field(
        0.0, description="Confidence score for intent classification"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Extracted parameters (AWB, cities, weight, etc.)"
    )

    # Context Assembly
    conversation_history: List[Dict[str, Any]] = Field(
        default_factory=list, description="Previous messages in conversation"
    )
    file_context: Dict[str, Any] = Field(
        default_factory=dict, description="Uploaded files and extracted data"
    )
    semantic_context: Dict[str, Any] = Field(
        default_factory=dict, description="RAG-retrieved context for FAQ"
    )

    # Agent Execution
    agent_name: Optional[str] = Field(
        None, description="Agent that will handle/processed the request"
    )
    agent_response: Optional[Dict[str, Any]] = Field(
        None, description="Raw response from the specialized agent"
    )

    # Final Output
    content: str = Field("", description="Final formatted response content")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (status, error codes, etc.)"
    )

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True
        extra = "allow"  # Allow additional fields for flexibility
