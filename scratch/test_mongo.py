import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load .env
load_dotenv(dotenv_path="/app/.env")

async def test_mongodb():
    db_url = os.getenv("DB_URL")
    print(f"Connecting to MongoDB with URL: {db_url}")
    if not db_url:
        print("❌ DB_URL not found in environment!")
        return
    try:
        client = AsyncIOMotorClient(db_url)
        # Ping the database
        await client.admin.command('ping')
        db = client.get_default_database()
        print(f"✅ Successfully connected to MongoDB Atlas! Default database: {db.name}")
        
        # Check collections
        collections = await db.list_collection_names()
        print(f"✅ Existing collections: {collections}")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_mongodb())
