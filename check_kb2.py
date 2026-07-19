import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb+srv://admin:Admin%40123@cluster0.p1bke.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
    db = client.get_default_database()
    # Check agents
    print("--- Agents ---")
    agents = await db['agents'].find().to_list(length=2)
    for agent in agents:
        print(f"Agent: {agent.get('_id')}, name: {agent.get('name')}, agentId: {agent.get('agentId')}")
        
    print("--- KB Documents ---")
    docs = await db['agent_kb_documents'].find().to_list(length=5)
    for doc in docs:
        print(doc)
    print(f"Total docs: {len(docs)}")

asyncio.run(check())
