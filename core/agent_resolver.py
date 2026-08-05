import logging
import re
from bson import ObjectId
from core.mongo_manager import mongo_db
from controllers.bot_controller import get_company_id_by_phone

logger = logging.getLogger(__name__)

async def resolve_agent_config(destination_id: str) -> dict | None:
    """
    Resolves the voice agent configuration based on the incoming SIP destination ID or phone number.
    """
    if not mongo_db.client or not destination_id:
        return None
        
    try:
        db = mongo_db.client.get_default_database()
        collections_to_search = ['exotel_agents', 'agents']
        
        for coll_name in collections_to_search:
            agents_collection = db[coll_name]
            
            # 1. Search directly by custom agentId
            agent = await agents_collection.find_one({"agentId": destination_id, "status": "active"})
            if agent:
                logger.info(f"🎯 Dynamic agent resolved by Agent ID in {coll_name}: {agent.get('name')} ({agent.get('agentId')})")
                return agent
    
            # 2. Search by MongoDB _id (string or ObjectId)
            agent = await agents_collection.find_one({"_id": destination_id, "status": "active"})
            if not agent and ObjectId.is_valid(destination_id):
                agent = await agents_collection.find_one({"_id": ObjectId(destination_id), "status": "active"})
            if agent:
                logger.info(f"🎯 Dynamic agent resolved by MongoDB _id in {coll_name}: {agent.get('name')} ({agent.get('agentId')})")
                return agent
    
            # 3. Search by assigned phoneNumber in MongoDB (exact match)
            agent = await agents_collection.find_one({"phoneNumber": destination_id})
            if agent:
                logger.info(f"🎯 Dynamic agent resolved by Phone Number in {coll_name}: {agent.get('name')} ({agent.get('agentId')})")
                return agent
    
            # 4. Search by digits of phoneNumber (last 10 digits regex match)
            clean_10 = re.sub(r'\D', '', str(destination_id))[-10:] if destination_id else ""
            if clean_10 and len(clean_10) >= 7:
                agent = await agents_collection.find_one({"phoneNumber": {"$regex": clean_10}})
                if agent:
                    logger.info(f"🎯 Dynamic agent resolved by Phone Number Regex ({clean_10}) in {coll_name}: {agent.get('name')} ({agent.get('agentId')})")
                    return agent
                
            # 5. Search by phone number mapping (using Company SQL lookup)
            company_id = await get_company_id_by_phone(destination_id)
            if company_id:
                # Load the active agent bound to this phone or the most recently updated active agent
                if clean_10:
                    agent = await agents_collection.find_one(
                        {"phoneNumber": {"$regex": clean_10}, "enterprise": company_id, "status": "active"}
                    )
                if not agent:
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
                    logger.info(f"🎯 Dynamic agent resolved for company {company_id} via phone {destination_id} in {coll_name}: {agent.get('name')}")
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

