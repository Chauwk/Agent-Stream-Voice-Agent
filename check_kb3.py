import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb+srv://chauwk:chauwk123@cluster0.phrdp.mongodb.net/chauwk?retryWrites=true&w=majority')
    db = client.get_default_database()
    
    print("--- KB Documents ---")
    docs = await db['agent_kb_documents'].find().to_list(length=10)
    for doc in docs:
        print(doc)
    print(f"Total docs: {len(docs)}")

asyncio.run(check())
