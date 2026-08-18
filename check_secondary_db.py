import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb+srv://admin:Admin%40123@cluster0.p1bke.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
    dbs = await client.list_database_names()
    print("Databases:", dbs)
    for db_name in dbs:
        db = client[db_name]
        cols = await db.list_collection_names()
        if 'agent_kb_documents' in cols:
            kb_ids = ['1785558212', '1785558935', '1785559250']
            print(f"Found collection in DB: {db_name}")
            docs = await db['agent_kb_documents'].find({"_id": {"$in": kb_ids}}).to_list(length=100)
            if not docs:
                docs = await db['agent_kb_documents'].find({"agentId": "6a6cd636940c832a99bb9855"}).to_list(length=100)
            print(f"Total docs found: {len(docs)}")
            for doc in docs:
                print(f"Doc ID: {doc.get('_id')}, text/content length: {len(str(doc))}, fileUrl: {doc.get('fileUrl')}")

asyncio.run(check())
