"""
Storage service for Huawei Cloud OBS (Object Storage Service).

Handles file uploads, downloads, and metadata management for
conversation context, uploaded files, and processed documents.

Uses Huawei's official OBS SDK (esdk-obs-python) for reliable OBS operations.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional
from uuid import uuid4

from obs import ObsClient
# ObsException is raised directly from ObsClient methods, catch as Exception

from ..config.settings import get_settings
from ..logging_config import logger

settings = get_settings()


class SMSAAIAssistantStorageClient:
    """
    Client for Huawei Cloud OBS storage operations.

    Uses Huawei's official OBS SDK (esdk-obs-python) for reliable operations.
    All operations are wrapped in async for compatibility with FastAPI.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        """
        Initialize OBS storage client.

        Args:
            endpoint: OBS endpoint URL (e.g., obs.me-east-1.myhuaweicloud.com)
            access_key_id: OBS Access Key ID
            secret_access_key: OBS Secret Access Key
            bucket_name: OBS bucket name
            region: OBS region (e.g., me-east-1)
        """
        self.endpoint = endpoint or settings.huawei_obs_endpoint
        self.access_key_id = access_key_id or settings.huawei_obs_access_key_id
        self.secret_access_key = secret_access_key or settings.huawei_obs_secret_access_key
        self.bucket_name = bucket_name or settings.huawei_obs_bucket_name
        self.region = region or settings.huawei_obs_region
        self.access_domain = settings.huawei_obs_access_domain

        # Initialize Huawei OBS client
        self._obs_client: Optional[ObsClient] = None

    def _get_obs_client(self) -> ObsClient:
        """Get or create Huawei OBS client."""
        if self._obs_client is None:
            # Construct server URL from endpoint
            server = f"https://{self.endpoint}"
            
            self._obs_client = ObsClient(
                access_key_id=self.access_key_id,
                secret_access_key=self.secret_access_key,
                server=server,
            )
        return self._obs_client

    async def upload_file(
        self,
        file_path: str,
        object_key: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to OBS.

        Args:
            file_path: Local file path to upload
            object_key: OBS object key (path in bucket). Auto-generated if not provided.
            content_type: MIME type (auto-detected if not provided)

        Returns:
            Dict with 'object_key', 'url', 'size', 'etag'
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Auto-generate object key if not provided
        if not object_key:
            object_key = f"uploads/{uuid4()}/{path.name}"

        # Auto-detect content type
        if not content_type:
            content_type, _ = mimetypes.guess_type(str(path))
            if not content_type:
                content_type = "application/octet-stream"

        # Upload using file path
        obs_client = self._get_obs_client()

        def _upload() -> Dict[str, Any]:
            """Synchronous upload function to run in executor."""
            try:
                # Use Huawei OBS SDK's putFile method (bulletproof)
                resp = obs_client.putFile(
                    bucketName=self.bucket_name,
                    objectKey=object_key,
                    file_path=str(path),
                    metadata={"ContentType": content_type},
                )

                # Build public URL using access domain
                url = f"https://{self.access_domain}/{object_key}"

                return {
                    "object_key": object_key,
                    "url": url,
                    "size": path.stat().st_size,
                    "etag": resp.get("etag", "").strip('"'),
                    "content_type": content_type,
                }
            except Exception as e:
                logger.error("obs_upload_error", error=str(e), object_key=object_key)
                raise RuntimeError(f"Failed to upload to OBS: {e}") from e

        # Run in executor to avoid blocking
        result = await asyncio.to_thread(_upload)
        logger.info("obs_upload_success", object_key=object_key, file_path=str(path))
        return result

    async def upload_bytes(
        self,
        file_bytes: bytes,
        object_key: str,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload file bytes to OBS.

        Uses temporary file approach with Huawei OBS SDK's putFile method.
        This is the bulletproof method that enterprise teams use.

        Args:
            file_bytes: File content as bytes
            object_key: OBS object key
            content_type: MIME type (defaults to application/octet-stream)

        Returns:
            Dict with 'object_key', 'url', 'size', 'etag', 'content_type'
        """
        if not content_type:
            content_type = "application/octet-stream"

        obs_client = self._get_obs_client()
        tmp_path: Optional[str] = None

        def _upload() -> Dict[str, Any]:
            """Synchronous upload function to run in executor."""
            nonlocal tmp_path
            try:
                # Step 1: Save uploaded bytes to temporary file
                # This avoids async/sync incompatibility issues
                suffix = ""  # No extension needed for temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                # Step 2: Upload using Huawei OBS SDK's putFile method (bulletproof)
                resp = obs_client.putFile(
                    bucketName=self.bucket_name,
                    objectKey=object_key,
                    file_path=tmp_path,
                    metadata={"ContentType": content_type},
                )

                # Build public URL using access domain
                url = f"https://{self.access_domain}/{object_key}"

                return {
                    "object_key": object_key,
                    "url": url,
                    "size": len(file_bytes),
                    "etag": resp.get("etag", "").strip('"'),
                    "content_type": content_type,
                }
            except Exception as e:
                logger.error("obs_upload_error", error=str(e), object_key=object_key)
                raise RuntimeError(f"Failed to upload to OBS: {e}") from e
            finally:
                # Step 3: Delete temp file
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception as cleanup_error:
                        logger.warning("temp_file_cleanup_failed", error=str(cleanup_error), path=tmp_path)

        # Run in executor to avoid blocking
        result = await asyncio.to_thread(_upload)
        logger.info("obs_upload_success", object_key=object_key, size=len(file_bytes))
        return result

    async def get_file_url(
        self, object_key: str, expires_in: int = 3600
    ) -> str:
        """
        Get a presigned URL for file access.

        Args:
            object_key: OBS object key
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL
        """
        obs_client = self._get_obs_client()

        def _generate_url() -> str:
            """Generate presigned URL synchronously."""
            try:
                resp = obs_client.createSignedUrl(
                    method="GET",
                    bucketName=self.bucket_name,
                    objectKey=object_key,
                    expires=expires_in,
                )
                return resp.get("signedUrl", "")
            except Exception as e:
                logger.error("obs_presigned_url_error", error=str(e), object_key=object_key)
                raise RuntimeError(f"Failed to generate presigned URL: {e}") from e

        return await asyncio.to_thread(_generate_url)

    async def delete_file(self, object_key: str) -> bool:
        """
        Delete a file from OBS.

        Args:
            object_key: OBS object key

        Returns:
            True if successful, False otherwise
        """
        obs_client = self._get_obs_client()

        def _delete() -> bool:
            """Delete file synchronously."""
            try:
                obs_client.deleteObject(
                    bucketName=self.bucket_name,
                    objectKey=object_key,
                )
                logger.info("obs_delete_success", object_key=object_key)
                return True
            except Exception as e:
                logger.error("obs_delete_error", error=str(e), object_key=object_key)
                return False

        return await asyncio.to_thread(_delete)

    async def store_conversation_context(
        self, conversation_id: str, context: Dict[str, Any]
    ) -> str:
        """
        Store conversation context JSON in OBS.

        Args:
            conversation_id: Conversation identifier
            context: Context dict to store

        Returns:
            OBS object key
        """
        object_key = f"conversations/{conversation_id}/context.json"
        context_bytes = json.dumps(context, indent=2).encode("utf-8")
        
        await self.upload_bytes(
            context_bytes,
            object_key,
            content_type="application/json",
        )
        
        logger.info("obs_context_stored", conversation_id=conversation_id, object_key=object_key)
        return object_key

    async def get_conversation_context(
        self, conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve conversation context from OBS.

        Args:
            conversation_id: Conversation identifier

        Returns:
            Context dict or None if not found
        """
        object_key = f"conversations/{conversation_id}/context.json"
        obs_client = self._get_obs_client()

        def _download() -> Optional[bytes]:
            """Download file synchronously."""
            try:
                resp = obs_client.getObject(
                    bucketName=self.bucket_name,
                    objectKey=object_key,
                )
                return resp.get("body").read()
            except Exception as e:
                error_code = e.get("code", "")
                if error_code == "NoSuchKey":
                    logger.info("obs_context_not_found", conversation_id=conversation_id)
                    return None
                logger.error("obs_context_download_error", error=str(e), conversation_id=conversation_id)
                raise RuntimeError(f"Failed to download context: {e}") from e

        try:
            content_bytes = await asyncio.to_thread(_download)
            if content_bytes is None:
                return None
            
            context = json.loads(content_bytes.decode("utf-8"))
            logger.info("obs_context_retrieved", conversation_id=conversation_id)
            return context
        except Exception as e:
            logger.error("obs_context_parse_error", error=str(e), conversation_id=conversation_id)
            return None
