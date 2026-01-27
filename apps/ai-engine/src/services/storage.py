from __future__ import annotations

from typing import Any, Dict


class StorageClient:
    """
    Placeholder S3-compatible storage client.

    In future phases this will manage:
    - Uploading files (images, PDFs) to S3/MinIO
    - Generating signed URLs for secure access
    - Storing and retrieving conversation-related artifacts
    """

    def __init__(self, bucket_name: str | None = None) -> None:
        self._bucket_name = bucket_name or "smsa-ai-files"

    async def upload_file(self, *, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Upload a file and return metadata (currently a stub).
        """
        return {
            "fileId": filename,
            "bucket": self._bucket_name,
            "url": f"https://placeholder-storage/{self._bucket_name}/{filename}",
        }

    async def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Retrieve file metadata (currently a stub).
        """
        return {
            "fileId": file_id,
            "bucket": self._bucket_name,
        }


