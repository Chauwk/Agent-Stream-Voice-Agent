import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

async def check():
    client = AsyncIOMotorClient('mongodb+srv://chauwk:chauwk123@cluster0.phrdp.mongodb.net/chauwk?retryWrites=true&w=majority')
    db = client.get_default_database()
    
    agent_id = "6a6cd636940c832a99bb9855"
    print(f"--- Checking Agent {agent_id} ---")
    
    agent = None
    collections_to_check = ["agents", "exotel_agents", "modernexotelaiagents", "modernaiagents"]
    
    for coll in collections_to_check:
        agent = await db[coll].find_one({"_id": ObjectId(agent_id)})
        if not agent:
            agent = await db[coll].find_one({"_id": agent_id})
        if agent:
            print(f"Agent found in collection: {coll}")
            break
            
    if not agent:
        # Try finding by name "Shakti"
        for coll in collections_to_check:
            agent = await db[coll].find_one({"name": {"$regex": "Shakti", "$options": "i"}})
            if agent:
                print(f"Agent found by name in collection: {coll}, id: {agent.get('_id')}")
                break

    if agent:
        print(f"Agent Name: {agent.get('name')}")
        print(f"Agent Enterprise: {agent.get('enterprise')}")
        print(f"Instructions:\n{agent.get('instructions')}")
        
        kb_ids = agent.get('knowledgeBaseIds', [])
        print(f"Knowledge Base IDs: {kb_ids}")
        
        # Check KB documents
        print(f"--- Checking KB Documents ---")
        docs = await db['agent_kb_documents'].find({"agentId": {"$in": [str(agent.get('_id')), agent.get('_id')]}}).to_list(length=100)
        if not docs and kb_ids:
            docs = await db['agent_kb_documents'].find({"_id": {"$in": [ObjectId(k) for k in kb_ids if ObjectId.is_valid(k)] + kb_ids}}).to_list(length=100)
            
        print(f"Total docs found: {len(docs)}")
        for doc in docs:
            print(f"Doc ID: {doc.get('_id')}, filename: {doc.get('fileName') or doc.get('filename')}, fileUrl: {doc.get('fileUrl')}, status: {doc.get('status')}")

asyncio.run(check())
