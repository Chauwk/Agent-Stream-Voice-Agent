from motor.motor_asyncio import AsyncIOMotorClient
from config import Config
import logging

logger = logging.getLogger(__name__)

class MongoManager:
    def __init__(self):
        try:
            if not Config.DB_URL:
                logger.warning("⚠️ DB_URL not set in configurations. Call logs will not be saved.")
                self.client = None
                self.call_logs_collection = None
                return
            
            self.client = AsyncIOMotorClient(Config.DB_URL)
            self.db = self.client.get_default_database() # Uses the database name in the connection string
            self.call_logs_collection = self.db['Agent_Stream_CallsLogs']
            logger.info("✅ Connected to MongoDB Atlas successfully")
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            self.client = None
            self.call_logs_collection = None

    async def save_call_log(self, call_data: dict):
        if self.call_logs_collection is None:
            logger.warning("⚠️ Cannot save call log. MongoDB is not connected.")
            return
            
        try:
            await self.call_logs_collection.insert_one(call_data)
            logger.info(f"✅ Call log {call_data.get('call_id')} successfully saved to MongoDB")
        except Exception as e:
            logger.error(f"❌ Failed to save call log to MongoDB: {e}")

# Global instance
mongo_db = MongoManager()
