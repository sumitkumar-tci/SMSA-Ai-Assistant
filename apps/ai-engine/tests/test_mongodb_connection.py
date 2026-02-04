"""
MongoDB Connection Test Script

This script tests the MongoDB connection using the credentials from .env file.
Run this script to verify MongoDB integration before deploying to production.

Usage:
    python -m pytest tests/test_mongodb_connection.py -v
    OR
    python tests/test_mongodb_connection.py
    OR (recommended)
    python -m tests.test_mongodb_connection
"""

import asyncio
import sys
import os
from pathlib import Path

# Get the project root (SMSA-Ai-Assistant) - where .env file is
project_root = Path(__file__).parent.parent.parent.parent
ai_engine_root = Path(__file__).parent.parent
src_path = ai_engine_root / "src"

# Change to project root so .env file is found
os.chdir(project_root)

# Add src directory to path FIRST so relative imports work
sys.path.insert(0, str(src_path))

# Now import - the relative imports in db.py will work because src is in path
try:
    from services.db import SMSAAIAssistantDatabaseManager
    from config.settings import get_settings
    from logging_config import logger
except ImportError as e:
    # Fallback: try importing from src explicitly
    sys.path.insert(0, str(ai_engine_root))
    from src.services.db import SMSAAIAssistantDatabaseManager
    from src.config.settings import get_settings
    from src.logging_config import logger


async def test_mongodb_connection():
    """Test MongoDB connection and basic operations."""
    print("\n" + "="*60)
    print("MongoDB Connection Test")
    print("="*60 + "\n")
    
    settings = get_settings()
    print(f"📋 MongoDB URI: {settings.mongodb_uri[:50]}...")
    print(f"📋 Database Name: smsa-ai-assistant\n")
    
    db_manager = SMSAAIAssistantDatabaseManager()
    
    try:
        # Test 1: Connect to MongoDB
        print("🔌 Test 1: Connecting to MongoDB...")
        await db_manager.connect()
        print("✅ Connection successful!\n")
        
        # Test 2: Create a test conversation
        print("📝 Test 2: Creating test conversation...")
        test_user_id = "test-user-mongodb-integration"
        test_conv_id = await db_manager.create_conversation(
            user_id=test_user_id,
            metadata={"test": True, "integration_test": True}
        )
        print(f"✅ Conversation created: {test_conv_id}\n")
        
        # Test 3: Save a test message
        print("💬 Test 3: Saving test message...")
        message_id = await db_manager.save_message(
            conversation_id=test_conv_id,
            role="user",
            content="This is a test message for MongoDB integration",
            metadata={"test": True}
        )
        print(f"✅ Message saved: {message_id}\n")
        
        # Test 4: Save assistant response
        print("🤖 Test 4: Saving assistant response...")
        response_id = await db_manager.save_message(
            conversation_id=test_conv_id,
            role="assistant",
            content="This is a test response from the assistant",
            metadata={"agent": "system", "test": True}
        )
        print(f"✅ Response saved: {response_id}\n")
        
        # Test 5: Retrieve conversation history
        print("📚 Test 5: Retrieving conversation history...")
        history = await db_manager.get_conversation_history(test_conv_id, limit=10)
        print(f"✅ Retrieved {len(history)} messages")
        for i, msg in enumerate(history, 1):
            print(f"   {i}. [{msg['role']}] {msg['content'][:50]}...")
        print()
        
        # Test 6: Get conversation metadata
        print("📋 Test 6: Retrieving conversation metadata...")
        conv = await db_manager.get_conversation(test_conv_id)
        if conv:
            print(f"✅ Conversation found:")
            print(f"   - User ID: {conv.get('user_id')}")
            print(f"   - Status: {conv.get('status')}")
            print(f"   - Created: {conv.get('created_at')}")
        print()
        
        # Test 7: List user conversations
        print("📋 Test 7: Listing user conversations...")
        conversations = await db_manager.list_conversations(test_user_id, limit=5)
        print(f"✅ Found {len(conversations)} conversations for user")
        print()
        
        # Test 8: Ensure conversation exists
        print("🔍 Test 8: Testing ensure_conversation_exists...")
        existing_conv_id = "test-existing-conversation"
        result = await db_manager.ensure_conversation_exists(
            conversation_id=existing_conv_id,
            user_id=test_user_id,
            metadata={"test": True}
        )
        if result:
            print(f"✅ Conversation ensured: {existing_conv_id}")
        print()
        
        # Cleanup: Disconnect
        print("🧹 Cleaning up...")
        await db_manager.disconnect()
        print("✅ Disconnected from MongoDB\n")
        
        print("="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nMongoDB integration is working correctly!")
        print("You can now deploy to production.\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        
        try:
            await db_manager.disconnect()
        except:
            pass
        
        print("\n" + "="*60)
        print("❌ TESTS FAILED")
        print("="*60)
        print("\nPlease check:")
        print("1. MongoDB URI in .env file is correct")
        print("2. MongoDB server is accessible from this machine")
        print("3. Credentials are correct (username/password)")
        print("4. Network connectivity to MongoDB hosts")
        print("5. MongoDB replica set is running\n")
        
        return False


async def main():
    """Main entry point."""
    success = await test_mongodb_connection()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
