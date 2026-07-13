import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
import datetime

# Load env variables from the container path
load_dotenv(dotenv_path="/app/.env")

async def test_mongo_write():
    db_url = os.getenv("DB_URL")
    print(f"Connecting to MongoDB with URL: {db_url}")
    if not db_url:
        print("❌ DB_URL not found in environment!")
        return
        
    try:
        client = AsyncIOMotorClient(db_url)
        db = client.get_default_database()
        collection = db['Agent_Stream_CallsLogs']
        
        # Define a sample test call log document
        sample_log = {
            "call_id": "test-call-12345-abcde",
            "direction": "inbound",
            "from_number": "+1234567890",
            "to_number": "+0987654321",
            "duration_seconds": 15,
            "status": "completed",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "notes": "Sample test log to verify Agent_Stream_CallsLogs write permissions"
        }
        
        print("Inserting sample call log into 'Agent_Stream_CallsLogs'...")
        result = await collection.insert_one(sample_log)
        inserted_id = result.inserted_id
        print(f"✅ Successfully inserted document! ID: {inserted_id}")
        
        # Query it back to confirm
        print("Querying the inserted document back from database...")
        queried_doc = await collection.find_one({"_id": inserted_id})
        print(f"✅ Found document: {queried_doc}")
        
        # Delete it to keep the database clean
        print("Cleaning up the test document...")
        delete_result = await collection.delete_one({"_id": inserted_id})
        print(f"✅ Deleted {delete_result.deleted_count} test document(s).")
        
        print("🎉 MongoDB Read/Write Test Completed Successfully!")
    except Exception as e:
        print(f"❌ MongoDB read/write verification failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_mongo_write())
