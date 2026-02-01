from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator, Dict
from uuid import uuid4

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from pathlib import Path

from .models.tracking import ChatMessageRequest, TrackingSseEvent, TrackingSseMetadata
from .orchestrator.router import route_message
from .services.storage import SMSAAIAssistantStorageClient
from .services.vision_client import SMSAAIAssistantVisionClient
from .logging_config import logger

app = FastAPI(title="SMSA AI Engine")

# Initialize clients
_storage_client = SMSAAIAssistantStorageClient()
_vision_client = SMSAAIAssistantVisionClient()


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
        "selected_agent": body.selected_agent,
        "file_id": body.file_id,
        "file_url": body.file_url,
    }

    result = await route_message(context)

    # Get agent name from result, default to "tracking" for backwards compatibility
    agent_name = result.get("agent", "tracking")

    metadata = TrackingSseMetadata(
        agent=agent_name,  # type: ignore[arg-type]
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


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
) -> JSONResponse:
    """
    Upload a file to Huawei OBS and optionally process with Vision API.

    Accepts multipart/form-data with a file.
    For images, automatically extracts AWB and shipment details using Vision API.
    Returns the OBS object key, URL, and extracted data (if image).
    """
    try:
        # Read file content
        file_bytes = await file.read()
        
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty file not allowed")

        # Generate object key
        file_ext = ""
        if file.filename:
            file_ext = Path(file.filename).suffix
        object_key = f"uploads/{conversation_id or 'general'}/{uuid4()}{file_ext}"

        # Upload to OBS first
        result = await _storage_client.upload_bytes(
            file_bytes=file_bytes,
            object_key=object_key,
            content_type=file.content_type or "application/octet-stream",
        )

        logger.info(
            "file_uploaded",
            object_key=object_key,
            size=len(file_bytes),
            conversation_id=conversation_id,
            content_type=file.content_type,
        )

        # Process image with Vision API if it's an image
        extracted_data = None
        is_image = file.content_type and file.content_type.startswith("image/")
        
        if is_image:
            try:
                logger.info("processing_image_with_vision", object_key=object_key)
                # Extract AWB and shipment details from image
                extracted_data = await _vision_client.extract_awb_from_image(file_bytes)
                logger.info(
                    "vision_extraction_complete",
                    object_key=object_key,
                    awb=extracted_data.get("awb"),
                )
                
                # Store file metadata with extracted data in conversation context
                if conversation_id and extracted_data:
                    try:
                        # Get existing context or create new
                        existing_context = await _storage_client.get_conversation_context(
                            conversation_id
                        ) or {}
                        
                        # Update with file metadata
                        if "files" not in existing_context:
                            existing_context["files"] = {}
                        
                        existing_context["files"][object_key] = {
                            "object_key": object_key,
                            "url": result["url"],
                            "content_type": file.content_type,
                            "size": len(file_bytes),
                            "extracted_data": extracted_data,
                        }
                        
                        # Store updated context
                        await _storage_client.store_conversation_context(
                            conversation_id, existing_context
                        )
                        logger.info("file_context_stored", conversation_id=conversation_id, object_key=object_key)
                    except Exception as context_error:
                        logger.warning("context_storage_failed", error=str(context_error))
                        
            except Exception as vision_error:
                logger.warning(
                    "vision_processing_failed",
                    error=str(vision_error),
                    object_key=object_key,
                )
                # Don't fail the upload if vision processing fails
                extracted_data = {"error": f"Vision processing failed: {str(vision_error)}"}

        response_data = {
            "success": True,
            "object_key": result["object_key"],
            "url": result["url"],
            "size": result["size"],
            "content_type": result["content_type"],
        }

        # Add extracted data if available
        if extracted_data:
            response_data["extracted_data"] = extracted_data
            
            # If AWB was extracted, automatically track it and include tracking details
            if extracted_data.get("awb"):
                try:
                    from .agents.tracking import SMSAAIAssistantTrackingAgent
                    tracking_agent = SMSAAIAssistantTrackingAgent()
                    awb = extracted_data["awb"]
                    
                    # Track the shipment automatically using run method
                    tracking_result = await tracking_agent.run(
                        context={
                            "message": f"track AWB {awb}",
                            "conversation_id": conversation_id or "general",
                        },
                    )
                    
                    # Add tracking details to response
                    if tracking_result and tracking_result.get("content"):
                        response_data["tracking_details"] = tracking_result["content"]
                        logger.info("auto_tracked_from_vision", awb=awb)
                except Exception as auto_track_error:
                    logger.warning("auto_track_failed", error=str(auto_track_error), exc_info=True)
                    # Don't fail the upload if auto-tracking fails

        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error("file_upload_error", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "smsa-ai-engine"}

