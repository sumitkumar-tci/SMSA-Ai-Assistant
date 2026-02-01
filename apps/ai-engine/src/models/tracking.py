from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, List, Any

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    user_id: Optional[str] = Field(default=None, alias="userId")
    message: str
    explicit_intent: Optional[Literal["TRACKING", "RATES", "LOCATIONS", "FAQ"]] = Field(
        default=None, alias="explicitIntent"
    )
    selected_agent: Optional[Literal["tracking", "rates", "retail", "faq"]] = Field(
        default=None, alias="selectedAgent"
    )
    file_id: Optional[str] = Field(default=None, alias="fileId")  # OBS object key for uploaded file
    file_url: Optional[str] = Field(default=None, alias="fileUrl")  # Direct file URL


class TrackingRequestPayload(BaseModel):
    awbs: List[str]
    language: Optional[Literal["en", "ar"]] = "en"


class TrackingCheckpoint(BaseModel):
    timestamp: datetime
    location: str
    description: str
    status_code: Optional[str] = Field(default=None, alias="statusCode")


TrackingStatus = Literal[
    "PENDING",
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "EXCEPTION",
    "UNKNOWN",
]


class TrackingResult(BaseModel):
    awb: str
    status: TrackingStatus
    current_location: Optional[str] = Field(default=None, alias="currentLocation")
    eta: Optional[datetime] = None
    checkpoints: List[TrackingCheckpoint] = []
    raw_response: Optional[Any] = Field(default=None, alias="rawResponse")
    error_code: Optional[str] = Field(default=None, alias="errorCode")
    error_message: Optional[str] = Field(default=None, alias="errorMessage")


SseEventType = Literal["token", "done", "error"]


class TrackingSseMetadata(BaseModel):
    agent: Literal["tracking", "rates", "retail", "faq", "system"]
    timestamp: datetime
    conversation_id: str = Field(..., alias="conversationId")


class TrackingSseEvent(BaseModel):
    type: SseEventType
    content: str
    metadata: TrackingSseMetadata

