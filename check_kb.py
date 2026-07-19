import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb+srv://venkatsubramanianh:5V7h98JIfgBIfwT4@cluster0.p1bke.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
    db = client.get_default_database()
    docs = await db['agent_kb_documents'].find().to_list(length=10)
    for doc in docs:
        print(doc)
    print(f"Total docs: {len(docs)}")

asyncio.run(check())
