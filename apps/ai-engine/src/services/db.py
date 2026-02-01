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
            db_name = "smsa_ai_assistant"
            if "/" in self.connection_string:
                # Extract from mongodb://host:port/dbname
                parts = self.connection_string.split("/")
                if len(parts) > 3:
                    db_name = parts[-1].split("?")[0]  # Remove query params
            self._db = self._client[db_name]

    async def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    async def create_conversation(
        self, user_id: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new conversation.

        Args:
            user_id: User identifier
            metadata: Optional conversation metadata

        Returns:
            Conversation ID (generated UUID)
        """
        import uuid

        await self.connect()

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
