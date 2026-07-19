import logging
from bson import ObjectId
from core.mongo_manager import mongo_db
from controllers.bot_controller import get_company_id_by_phone

logger = logging.getLogger(__name__)

async def resolve_agent_config(destination_id: str) -> dict | None:
    """
    Resolves the voice agent configuration based on the incoming SIP destination ID.
    
    1. First tries to find the agent by exact agentId or MongoDB ObjectId.
    2. If not found, looks up the company ID (enterprise ID) using the destination_id 
       as a phone number, and retrieves the active agent configured for that company.
    """
    if not mongo_db.client:
        logger.warning("⚠️ MongoDB client offline, cannot resolve agent config dynamically.")
        return None
        
    try:
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        
        # 1. Search directly by custom agentId
        agent = await agents_collection.find_one({"agentId": destination_id, "status": "active"})
        if agent:
            logger.info(f"🎯 Dynamic agent resolved by Agent ID: {agent.get('name')} ({agent.get('agentId')})")
            return agent

        # 1.5 Search by assigned phoneNumber in MongoDB
        agent = await agents_collection.find_one({"phoneNumber": destination_id, "status": "active"})
        if agent:
            logger.info(f"🎯 Dynamic agent resolved by Phone Number: {agent.get('name')} ({agent.get('agentId')})")
            return agent
            
        # 2. Search by MongoDB string _id (agents store _id as string, not ObjectId)
        agent = await agents_collection.find_one({"_id": destination_id, "status": "active"})
        if agent:
            logger.info(f"🎯 Dynamic agent resolved by MongoDB _id: {agent.get('name')} ({agent.get('agentId')})")
            return agent
            
        # 3. Search by phone number mapping (using Company SQL lookup)
        company_id = await get_company_id_by_phone(destination_id)
        if company_id:
            # Load the most recently updated active agent belonging to this company/enterprise
            # Support both 'enterprise' (new field) and 'company_id' (legacy field)
            agent = await agents_collection.find_one(
                {"enterprise": company_id, "status": "active"},
                sort=[("updatedAt", -1)]
            )
            if not agent:
                agent = await agents_collection.find_one(
                    {"company_id": company_id, "status": "active"},
                    sort=[("updatedAt", -1)]
                )
            if agent:
                logger.info(f"🎯 Dynamic agent resolved for company {company_id} via phone {destination_id}: {agent.get('name')}")
                return agent
                
    except Exception as e:
        logger.error(f"❌ Failed to resolve agent config: {e}")
        
    return None

async def get_company_name(company_id: str) -> str | None:
    """Helper to query MongoDB database for company name by ID"""
    if not mongo_db.client:
        return None
    try:
        db = mongo_db.client.get_default_database()
        companies_collection = db['companies']
        company = await companies_collection.find_one({"company_id": company_id})
        if company:
            return company.get("name")
    except Exception as e:
        logger.error(f"Failed to lookup company name in MongoDB for ID {company_id}: {e}")
    return None

