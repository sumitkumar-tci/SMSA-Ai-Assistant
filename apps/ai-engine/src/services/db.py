"""
Database service for MongoDB/DDS integration.

Handles conversation history, message storage, and user data
using Motor (async MongoDB driver).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from ..config.settings import get_settings

settings = get_settings()


class SMSAAIAssistantDatabaseManager:
    """
    Database manager for MongoDB/DDS operations.

    Supports:
    - Conversation management
    - Message storage and retrieval
    - User data management
    - Analytics tracking
    """

    def __init__(self, connection_string: Optional[str] = None) -> None:
        """
        Initialize database manager.

        Args:
            connection_string: MongoDB connection string (defaults to settings)
        """
        self.connection_string = connection_string or settings.mongodb_uri
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self) -> None:
        """Connect to MongoDB."""
        if self._client is None:
            self._client = AsyncIOMotorClient(self.connection_string)
            # Extract database name from connection string or use default
            # Format: mongodb://[username:password@]host[:port][,host2:port2]/database[?options]
            db_name = "smsa-ai-assistant"  # Default database name
            try:
                # Parse connection string to extract database name
                # Remove mongodb:// prefix
                uri = self.connection_string.replace("mongodb://", "")
                # Split by / to get database part
                if "/" in uri:
                    db_part = uri.split("/")[-1]  # Get last part after /
                    # Remove query parameters (everything after ?)
                    if "?" in db_part:
                        db_name = db_part.split("?")[0]
                    else:
                        db_name = db_part
                    # If database name is empty, use default
                    if not db_name:
                        db_name = "smsa-ai-assistant"
            except Exception as e:
                # If parsing fails, use default
                from ..logging_config import logger
                logger.warning("mongodb_db_name_extraction_failed", error=str(e), using_default=db_name)
            self._db = self._client[db_name]

    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    async def create_conversation(
        self, user_id: str, metadata: Optional[Dict[str, Any]] = None, conversation_id: Optional[str] = None
    ) -> str:
        """
        Create a new conversation.

        Args:
            user_id: User identifier
            metadata: Optional conversation metadata
            conversation_id: Optional conversation ID (if not provided, generates UUID)

        Returns:
            Conversation ID
        """
        import uuid

        await self.connect()

        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
        
        conversation = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "status": "active",
            "metadata": metadata or {},
        }

        try:
            await self._db.conversations.insert_one(conversation)
            return conversation_id
        except PyMongoError as e:
            raise RuntimeError(f"Failed to create conversation: {e}") from e

    async def ensure_conversation_exists(
        self, conversation_id: str, user_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Ensure a conversation exists, creating it if it doesn't.

        Args:
            conversation_id: Conversation identifier
            user_id: User identifier
            metadata: Optional conversation metadata

        Returns:
            True if conversation exists or was created, False otherwise
        """
        try:
            existing = await self.get_conversation(conversation_id)
            if existing:
                return True
            
            # Create conversation with specified ID
            await self.create_conversation(
                user_id=user_id,
                metadata=metadata,
                conversation_id=conversation_id,
            )
            return True
        except Exception as e:
            from ..logging_config import logger
            logger.warning("ensure_conversation_failed", error=str(e), conversation_id=conversation_id)
            return False

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Save a message to a conversation.

        Args:
            conversation_id: Conversation identifier
            role: Message role ('user' or 'assistant')
            content: Message content
            metadata: Optional message metadata (intent, agent, etc.)

        Returns:
            Message ID
        """
        import uuid

        await self.connect()

        message_id = str(uuid.uuid4())
        message = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {},
        }

        try:
            await self._db.messages.insert_one(message)

            # Update conversation's updated_at timestamp
            await self._db.conversations.update_one(
                {"conversation_id": conversation_id},
                {"$set": {"updated_at": datetime.utcnow()}},
            )

            return message_id
        except PyMongoError as e:
            raise RuntimeError(f"Failed to save message: {e}") from e

    async def get_conversation_history(
        self, conversation_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Retrieve conversation message history.

        Args:
            conversation_id: Conversation identifier
            limit: Maximum number of messages to retrieve

        Returns:
            List of message dicts ordered by timestamp
        """
        await self.connect()

        try:
            cursor = self._db.messages.find(
                {"conversation_id": conversation_id}
            ).sort("timestamp", 1).limit(limit)

            messages = []
            async for doc in cursor:
                messages.append({
                    "role": doc.get("role"),
                    "content": doc.get("content"),
                    "timestamp": doc.get("timestamp"),
                    "metadata": doc.get("metadata", {}),
                })

            return messages
        except PyMongoError as e:
            raise RuntimeError(f"Failed to retrieve conversation history: {e}") from e

    async def get_conversation(
        self, conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get conversation metadata.

        Args:
            conversation_id: Conversation identifier

        Returns:
            Conversation dict or None if not found
        """
        await self.connect()

        try:
            doc = await self._db.conversations.find_one(
                {"conversation_id": conversation_id}
            )
            if doc:
                doc.pop("_id", None)  # Remove MongoDB _id
            return doc
        except PyMongoError as e:
            raise RuntimeError(f"Failed to retrieve conversation: {e}") from e

    async def list_conversations(
        self, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        List user's conversations.

        Args:
            user_id: User identifier
            limit: Maximum number of conversations

        Returns:
            List of conversation dicts
        """
        await self.connect()

        try:
            cursor = self._db.conversations.find(
                {"user_id": user_id}
            ).sort("updated_at", -1).limit(limit)

            conversations = []
            async for doc in cursor:
                doc.pop("_id", None)
                conversations.append(doc)

            return conversations
        except PyMongoError as e:
            raise RuntimeError(f"Failed to list conversations: {e}") from e
