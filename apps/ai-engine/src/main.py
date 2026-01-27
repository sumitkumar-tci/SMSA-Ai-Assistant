from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator, Dict

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from .models.tracking import ChatMessageRequest, TrackingSseEvent, TrackingSseMetadata
from .orchestrator.router import route_message


app = FastAPI(title="SMSA AI Engine")


async def _stream_tracking_response(
    body: ChatMessageRequest,
) -> AsyncIterator[bytes]:
    """
    Wraps the orchestrator response in a text/event-stream compatible generator.
    """
    context: Dict[str, Any] = {
        "conversation_id": body.conversation_id,
        "user_id": body.user_id,
        "message": body.message,
        "explicit_intent": body.explicit_intent,
    }

    result = await route_message(context)

    metadata = TrackingSseMetadata(
        agent="tracking",
        timestamp=datetime.utcnow(),
        conversationId=body.conversation_id,  # type: ignore[call-arg]
    )

    # Single token event with the full message content for now
    token_event = TrackingSseEvent(
        type="token",
        content=result.get("content", ""),
        metadata=metadata,
    )
    yield f"data: {token_event.model_dump_json(by_alias=True)}\n\n".encode("utf-8")

    # Done event
    done_event = TrackingSseEvent(
        type="done",
        content="",
        metadata=metadata,
    )
    yield f"data: {done_event.model_dump_json(by_alias=True)}\n\n".encode("utf-8")


@app.post("/orchestrator/chat")
async def orchestrator_chat(body: ChatMessageRequest) -> StreamingResponse:
    """
    Primary entrypoint for the API gateway to call the AI engine.

    Returns a Server-Sent Events (SSE) stream with TrackingSseEvent payloads.
    """

    async def event_stream() -> AsyncIterator[bytes]:
        async for chunk in _stream_tracking_response(body):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


