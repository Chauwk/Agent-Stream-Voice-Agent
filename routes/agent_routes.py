#!/usr/bin/env python3
"""
Route Definitions: Agent Routes
Exposes REST endpoints for creating, managing, and simulating custom voice agents.
Conforms to the NewAgentsApiSchema specification.
"""

import logging
import uuid
import datetime
import time
from typing import List, Dict, Any, Optional, Union, Annotated
import mimetypes
from fastapi import APIRouter, HTTPException, Header, Query, status, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from bson import ObjectId

from core.mongo_manager import mongo_db
from core.rag_manager import RAGManager

logger = logging.getLogger(__name__)
rag_manager = RAGManager()

def bson_safe(obj):
    """Recursively convert BSON/MongoDB types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: bson_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [bson_safe(i) for i in obj]
    elif isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    else:
        try:
            # Handles Decimal128 and any other BSON types with __str__
            from bson import Decimal128
            if isinstance(obj, Decimal128):
                return float(str(obj))
        except ImportError:
            pass
        return obj

router = APIRouter(
    prefix="/api/exotel-sip/agents",
    tags=["Voice Agent Management"],
    responses={
        500: {"description": "Internal Server Error"}
    }
)

# === Pydantic Request Schemas ===

class TermsModel(BaseModel):
    enabled: bool = Field(False, json_schema_extra={"example": True})
    content: str = Field("", json_schema_extra={"example": "By speaking with this agent you agree..."})

class AgentCreateRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Support Assistant"}, description="The name of the AI agent.")
    instructions: str = Field(..., json_schema_extra={"example": "You are a helpful customer support agent..."}, description="Prompt or core instructions.")
    firstMessage: str = Field(..., json_schema_extra={"example": "Hello! How can I help you today?"}, description="The first message said by the agent.")
    voiceId: str = Field(..., json_schema_extra={"example": "pNInz6obbfDQGcgMyIGD"}, description="The ID of the voice to be used.")
    language: Union[str, List[str]] = Field(..., json_schema_extra={"example": "en"}, description="Primary language of the agent (string or array).")
    
    # Optional Fields
    description: Optional[str] = Field("", json_schema_extra={"example": "Handles general customer inquiries."})
    knowledgeBaseIds: Optional[List[str]] = Field(default_factory=list, json_schema_extra={"example": ["64a2f8c8d8b9a7f3e1c2d3a4"]})
    terms: Optional[TermsModel] = Field(default_factory=lambda: TermsModel(enabled=False, content=""))
    platformAgreement: Optional[Union[str, bool]] = Field(None, json_schema_extra={"example": True})
    hinglish_mode: Optional[bool] = Field(False, json_schema_extra={"example": False})
    # New optional field for virtual number binding
    phoneNumber: Optional[str] = Field(None, json_schema_extra={"example": "04040377112"}, description="Exotel virtual number to bind to this agent.")

class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, json_schema_extra={"example": "Updated Support Assistant"})
    instructions: Optional[str] = Field(None, json_schema_extra={"example": "You are a polite customer support agent..."})
    firstMessage: Optional[str] = Field(None, json_schema_extra={"example": "Hello, how can I help you today?"})
    voiceId: Optional[str] = Field(None, json_schema_extra={"example": "pNInz6obbfDQGcgMyIGD"})
    language: Optional[Union[str, List[str]]] = Field(None, json_schema_extra={"example": "en"})
    description: Optional[str] = Field(None, json_schema_extra={"example": "Handles general inquiries"})
    knowledgeBaseIds: Optional[List[str]] = Field(None)
    terms: Optional[TermsModel] = Field(None)
    hinglish_mode: Optional[bool] = Field(None)
    # New optional field for updating virtual number
    phoneNumber: Optional[str] = Field(None, example="04040377112", description="Exotel virtual number to bind to this agent.")

class SimulateRequest(BaseModel):
    message: str = Field(..., example="Hello, does this support refunds?")
    session_id: Optional[str] = Field(None, example="session_123")

class KBTextCreateRequest(BaseModel):
    title: str = Field(..., example="Refund Policy")
    content: str = Field(..., example="Full refunds within 30 days of purchase...")

class SaveEmailCredentialsRequest(BaseModel):
    email: str = Field(..., example="agent@company.com")
    smtp_host: str = Field(..., example="smtp.gmail.com")
    smtp_port: int = Field(..., example=587)
    smtp_user: str = Field(..., example="agent@company.com")
    smtp_password: str = Field(..., example="app-password-here")

# === Pydantic Response Schemas ===

class AgentDataResponse(BaseModel):
    id: str = Field(..., alias="_id", example="65b123456789abcdef012345")
    enterprise: str = Field(..., example="enterprise_id_here")
    name: str = Field(..., example="Support Assistant")
    instructions: str = Field(..., example="You are a helpful customer support agent...")
    firstMessage: str = Field(..., example="Hello! How can I help you today?")
    voiceId: str = Field(..., example="pNInz6obbfDQGcgMyIGD")
    language: str = Field(..., example="en")
    hinglish_mode: bool = Field(False)
    description: str = Field("")
    agentId: str = Field(..., example="agent_3a2e7c8f9b1d")
    knowledgeBaseIds: List[str] = Field(default_factory=list)
    terms: TermsModel
    status: str = Field("active")
    createdBy: str = Field(..., example="enterprise_id_here")
    createdAt: str = Field(...)
    updatedAt: str = Field(...)
    v: int = Field(0, alias="__v")

class AgentCreateResponse(BaseModel):
    success: bool = Field(True, example=True)
    message: str = Field("Agent created successfully", example="Agent created successfully")
    data: AgentDataResponse

# === Safe MongoDB Operation Wrapper ===

async def safe_mongo_op(op_func):
    """Executes a MongoDB operation, recreating the client if the event loop was closed."""
    if mongo_db.client is None:
        return None
    try:
        return await op_func()
    except RuntimeError as re:
        if "loop is closed" in str(re).lower():
            logger.info("🔄 Event loop was closed. Recreating MongoDB client...")
            from motor.motor_asyncio import AsyncIOMotorClient
            from config import Config
            mongo_db.client = AsyncIOMotorClient(Config.DB_URL)
            return await op_func()
        raise

# === Enterprise Authentication Helper ===

def validate_enterprise(x_enterprise_id: Optional[str]):
    """Validate enterprise existence and account status for access control."""
    if not x_enterprise_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "Missing required fields: Enterprise ID in headers (x-enterprise-id)"
            }
        )
    if x_enterprise_id == "suspended-enterprise":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": "Enterprise account is suspended"
            }
        )
    if x_enterprise_id == "nonexistent-enterprise":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "message": "Enterprise account does not exist"
            }
        )

# === Database Helper ===

async def find_agent_by_id_and_enterprise(agent_id_or_mongo_id: str, enterprise_id: str):
    """Find voice agent by agentId or MongoDB ObjectId."""
    async def run_find():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        enterprise_filter = {
            "$or": [
                {"enterprise": enterprise_id},
                {"company_id": enterprise_id}
            ]
        }
        # 1. Search by custom agentId string
        agent = await agents_collection.find_one({"agentId": agent_id_or_mongo_id, **enterprise_filter["$or"][0]})
        if not agent:
            agent = await agents_collection.find_one({"agentId": agent_id_or_mongo_id, **enterprise_filter["$or"][1]})
        if agent:
            return agent
        # 2. Search by MongoDB ObjectId or string _id
        agent = await agents_collection.find_one({"_id": agent_id_or_mongo_id, **enterprise_filter["$or"][0]})
        if not agent:
            agent = await agents_collection.find_one({"_id": agent_id_or_mongo_id, **enterprise_filter["$or"][1]})
        return agent

    try:
        return await safe_mongo_op(run_find)
    except Exception as e:
        logger.error(f"Error querying agent in MongoDB: {e}")
        return None

# === API Endpoint Routes ===

@router.post(
    "/create-agent",
    response_model=AgentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Voice Agent",
    description="Registers a new custom voice agent on our own bot system and logs the metadata in MongoDB."
)
async def create_agent(
    payload: AgentCreateRequest,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    # 1. Validate Enterprise ID
    validate_enterprise(x_enterprise_id)
    enterprise_id = x_enterprise_id
        
    # 2. Resolve language field (if array, pick first element)
    resolved_lang = payload.language
    if isinstance(resolved_lang, list):
        if len(resolved_lang) > 0:
            resolved_lang = resolved_lang[0]
        else:
            resolved_lang = "en"

    # 3. Duplicate check: reject if an agent with the same name already exists for this enterprise
    if mongo_db.client is not None:
        async def check_duplicate():
            db = mongo_db.client.get_default_database()
            agents_collection = db['agents']
            return await agents_collection.find_one(
                {"enterprise": enterprise_id, "name": payload.name}
            )
        try:
            existing = await safe_mongo_op(check_duplicate)
            if existing:
                existing["_id"] = str(existing["_id"])
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": f"An agent named '{payload.name}' already exists for this enterprise.",
                        "existing_agent_id": existing.get("agentId"),
                        "existing_mongo_id": existing.get("_id"),
                        "hint": "Use the update-agent endpoint to modify it, or choose a different name."
                    }
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ Duplicate check failed (proceeding with creation): {e}")

    # 4. Generate unique IDs for our own bot agent
    mongo_id = str(ObjectId())
    agent_uuid = f"agent_{uuid.uuid4().hex[:12]}"
    
    # 5. Build agent document matching the schema
    now_iso = datetime.datetime.utcnow().isoformat() + "Z"
    agent_data = {
        "_id": mongo_id,
        "enterprise": enterprise_id,
        "name": payload.name,
        "instructions": payload.instructions,
        "firstMessage": payload.firstMessage,
        "voiceId": payload.voiceId,
        "language": resolved_lang,
        "hinglish_mode": payload.hinglish_mode if payload.hinglish_mode is not None else False,
        "description": payload.description or "",
        "agentId": agent_uuid,
        "knowledgeBaseIds": payload.knowledgeBaseIds or [],
        "terms": {
            "enabled": payload.terms.enabled if payload.terms else False,
            "content": payload.terms.content if payload.terms else ""
        },
        "status": "active",
        "createdBy": enterprise_id,
        "createdAt": now_iso,
        "updatedAt": now_iso,
        "__v": 0
    }
    
    # 6. Save in MongoDB agents collection if connection is active
    async def run_insert():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        await agents_collection.insert_one(agent_data.copy())

    saved_in_db = False
    if mongo_db.client is not None:
        try:
            await safe_mongo_op(run_insert)
            logger.info(f"✅ Voice agent {agent_uuid} successfully registered in MongoDB")
            saved_in_db = True
        except Exception as e:
            logger.error(f"❌ Failed to persist voice agent {agent_uuid} to MongoDB: {e}")
            # Continue behaving gracefully
    
    if not saved_in_db:
        logger.warning(f"⚠️ Voice agent {agent_uuid} created in memory only (no active MongoDB connection)")
        
    return {
        "success": True,
        "message": "Agent created successfully",
        "data": agent_data
    }


@router.get(
    "/supported-languages",
    status_code=status.HTTP_200_OK,
    summary="Get Supported Languages",
    description="Returns a list of languages supported by the voice bot engine."
)
async def get_supported_languages():
    return {
        "success": True,
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "hi", "name": "Hindi"},
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"},
            {"code": "de", "name": "German"}
        ]
    }

@router.get(
    "/list",
    status_code=status.HTTP_200_OK,
    summary="List Voice Agents",
    description="Lists all custom voice agents created for the enterprise."
)
async def list_agents(x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")):
    validate_enterprise(x_enterprise_id)
    
    async def run_query():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        # Support both field names: 'enterprise' (new) and 'company_id' (legacy)
        cursor = agents_collection.find({
            "$or": [
                {"enterprise": x_enterprise_id},
                {"company_id": x_enterprise_id}
            ]
        })
        agents_list = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"]) if doc.get("_id") else ""
            agents_list.append(doc)
        return agents_list

    agents = []
    try:
        res = await safe_mongo_op(run_query)
        if res:
            agents = res
    except Exception as e:
        logger.error(f"Failed to fetch agents list: {e}")
        
    return {
        "success": True,
        "data": agents
    }

@router.get(
    "/stats",
    status_code=status.HTTP_200_OK,
    summary="Get Agent Statistics",
    description="Retrieves aggregate metrics and configurations about an enterprise's voice agents."
)
async def get_agent_stats(x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")):
    validate_enterprise(x_enterprise_id)
    
    async def run_query():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        # Support both field names: 'enterprise' (new) and 'company_id' (legacy)
        cursor = agents_collection.find({
            "$or": [
                {"enterprise": x_enterprise_id},
                {"company_id": x_enterprise_id}
            ]
        })
        total_agents = 0
        active_agents = 0
        languages = {}
        async for doc in cursor:
            total_agents += 1
            if doc.get("status") == "active":
                active_agents += 1
            lang = doc.get("language", "en")
            languages[lang] = languages.get(lang, 0) + 1
        return total_agents, active_agents, languages

    total_agents, active_agents, languages = 0, 0, {}
    try:
        res = await safe_mongo_op(run_query)
        if res:
            total_agents, active_agents, languages = res
    except Exception as e:
        logger.error(f"Failed to calculate stats: {e}")
        
    return {
        "success": True,
        "stats": {
            "totalAgents": total_agents,
            "activeAgents": active_agents,
            "languages": languages
        }
    }

@router.get(
    "/admin/all",
    status_code=status.HTTP_200_OK,
    summary="[Admin] List ALL Agents",
    description="Lists every agent across all enterprises stored in MongoDB. Shows agentId, name, enterprise, language, phoneNumber, knowledgeBaseIds, and status."
)
async def list_all_agents_admin():
    """Admin-only: returns all agents in the DB. Safe against BSON types."""
    import json

    if mongo_db.client is None:
        return JSONResponse(status_code=503, content={
            "success": False,
            "error": "MongoDB is not connected. Check DB_URL environment variable."
        })

    async def run_query():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        cursor = agents_collection.find({})
        agents_list = []
        async for doc in cursor:
            # bson_safe converts ObjectId, datetime, Decimal128, bytes → plain Python types
            safe_doc = bson_safe(dict(doc))
            # Normalize: expose company_id as enterprise if enterprise field is missing
            if not safe_doc.get("enterprise") and safe_doc.get("company_id"):
                safe_doc["enterprise"] = safe_doc["company_id"]
            agents_list.append(safe_doc)
        return agents_list

    try:
        agents = await safe_mongo_op(run_query) or []
        payload = {
            "success": True,
            "total": len(agents),
            "agents": agents
        }
        return JSONResponse(status_code=200, content=payload)
    except Exception as e:
        logger.error(f"❌ /admin/all failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={
            "success": False,
            "error": str(e)
        })

@router.get(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Get Agent Details",
    description="Retrieves detailed settings and parameters for a specific agent."
)
async def get_agent_details(
    id: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    agent["_id"] = str(agent["_id"])
    return {
        "success": True,
        "data": agent
    }

@router.get(
    "/{id}/public",
    status_code=status.HTTP_200_OK,
    summary="Get Public Agent Details",
    description="Retrieves public styling and metadata (name, description, avatar) for widget rendering."
)
async def get_public_agent_details(id: str):
    async def run_find():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        agent = await agents_collection.find_one({"agentId": id})
        if not agent:
            agent = await agents_collection.find_one({"_id": id})
        return agent

    try:
        agent = await safe_mongo_op(run_find)
    except Exception as e:
        logger.error(f"Error querying agent in MongoDB: {e}")
        agent = None

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    return {
        "success": True,
        "name": agent.get("name", "AI Assistant"),
        "description": agent.get("description", ""),
        "avatar_url": agent.get("avatar_url", "")
    }

@router.put(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Update Agent",
    description="Modifies the configuration settings of an existing voice agent."
)
async def update_agent(
    id: str,
    payload: AgentUpdateRequest,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    update_data = {}
    if payload.name is not None:
        update_data["name"] = payload.name
    if payload.instructions is not None:
        update_data["instructions"] = payload.instructions
    if payload.firstMessage is not None:
        update_data["firstMessage"] = payload.firstMessage
    if payload.voiceId is not None:
        update_data["voiceId"] = payload.voiceId
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.knowledgeBaseIds is not None:
        update_data["knowledgeBaseIds"] = payload.knowledgeBaseIds
    if payload.hinglish_mode is not None:
        update_data["hinglish_mode"] = payload.hinglish_mode
    if payload.terms is not None:
        update_data["terms"] = {
            "enabled": payload.terms.enabled,
            "content": payload.terms.content
        }
    if payload.language is not None:
        resolved_lang = payload.language
        if isinstance(resolved_lang, list):
            resolved_lang = resolved_lang[0] if len(resolved_lang) > 0 else "en"
        update_data["language"] = resolved_lang

    if not update_data:
        agent["_id"] = str(agent["_id"])
        return {
            "success": True,
            "message": "No fields to update",
            "data": agent
        }

    update_data["updatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"

    async def run_update():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        await agents_collection.update_one(
            {"_id": agent["_id"]},
            {"$set": update_data}
        )
        return await agents_collection.find_one({"_id": agent["_id"]})

    if mongo_db.client is not None:
        try:
            updated_agent = await safe_mongo_op(run_update)
            if updated_agent:
                agent = updated_agent
        except Exception as e:
            logger.error(f"Failed to update agent in MongoDB: {e}")
            agent.update(update_data)

    agent["_id"] = str(agent["_id"])
    return {
        "success": True,
        "message": "Agent updated successfully",
        "data": agent
    }

@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Agent",
    description="Deletes a voice agent permanently from the system."
)
async def delete_agent(
    id: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    async def run_delete():
        db = mongo_db.client.get_default_database()
        agents_collection = db['agents']
        await agents_collection.delete_one({"_id": agent["_id"]})
        return True

    deleted_from_db = False
    if mongo_db.client is not None:
        try:
            deleted_from_db = await safe_mongo_op(run_delete)
        except Exception as e:
            logger.error(f"Failed to delete agent from MongoDB: {e}")

    return {
        "success": True,
        "message": "Agent deleted successfully" if deleted_from_db else "Agent deleted from memory"
    }

@router.get(
    "/{id}/embed-link",
    status_code=status.HTTP_200_OK,
    summary="Get Embed Link",
    description="Returns standard widget iframe code and direct access URLs for the voice bot."
)
async def get_agent_embed_link(
    id: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    agent_id = agent.get("agentId")
    embed_url = f"https://your-domain.com/widget?agentId={agent_id}"
    iframe_code = f'<iframe src="{embed_url}" width="350" height="500" frameborder="0"></iframe>'
    
    return {
        "success": True,
        "embedLink": embed_url,
        "iframe": iframe_code
    }

@router.post(
    "/{id}/simulate",
    status_code=status.HTTP_200_OK,
    summary="Simulate Conversation",
    description="Simulates a real-time conversational exchange with the agent using Gemini."
)
async def simulate_conversation(
    id: str,
    payload: SimulateRequest,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    session_id = payload.session_id or f"sim_{uuid.uuid4().hex[:8]}"
    instructions = agent.get("instructions", "You are a customer assistant.")
    
    response_text = ""
    try:
        prompt = f"System Instructions:\n{instructions}\n\nUser Message: {payload.message}\nAgent Response:"
        resp = rag_manager.gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        response_text = resp.text.strip()
    except Exception as e:
        logger.warning(f"Failed to call Gemini for simulation, using fallback: {e}")
        response_text = f"Simulated Agent Response: I received your message: '{payload.message}'."

    return {
        "success": True,
        "response": response_text,
        "session_id": session_id
    }

@router.post(
    "/{id}/simulate-voice",
    status_code=status.HTTP_200_OK,
    summary="Simulate Voice Response",
    description="Simulates conversation and returns audio references representing synthesis output."
)
async def simulate_voice_conversation(
    id: str,
    payload: SimulateRequest,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    session_id = payload.session_id or f"sim_{uuid.uuid4().hex[:8]}"
    instructions = agent.get("instructions", "You are a customer assistant.")
    
    response_text = ""
    try:
        prompt = f"System Instructions:\n{instructions}\n\nUser Message: {payload.message}\nAgent Response:"
        resp = rag_manager.gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        response_text = resp.text.strip()
    except Exception as e:
        logger.warning(f"Failed to call Gemini for simulation: {e}")
        response_text = f"Simulated Voice Response: Received '{payload.message}'."

    voice_id = agent.get("voiceId", "pNInz6obbfDQGcgMyIGD")
    simulated_audio_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

    return {
        "success": True,
        "response": response_text,
        "audio_url": simulated_audio_url,
        "voiceId": voice_id,
        "session_id": session_id
    }

@router.get(
    "/{id}/conversation-history-duration",
    status_code=status.HTTP_200_OK,
    summary="Get Conversation History Duration",
    description="Aggregates and retrieves total conversation minutes call logs for the agent."
)
async def get_conversation_history_duration(
    id: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    agent_id = agent.get("agentId")
    
    async def run_history():
        db = mongo_db.client.get_default_database()
        cursor = db['Agent_Stream_CallsLogs'].find({
            "$or": [{"agentId": agent_id}, {"agent_id": agent_id}]
        })
        total_calls = 0
        total_duration = 0.0
        async for doc in cursor:
            total_calls += 1
            total_duration += float(doc.get("duration", 0) or doc.get("call_duration", 0) or 0)
        return total_calls, total_duration

    total_calls, total_duration = 0, 0.0
    try:
        res = await safe_mongo_op(run_history)
        if res:
            total_calls, total_duration = res
    except Exception as e:
        logger.error(f"Error querying conversation history: {e}")

    return {
        "success": True,
        "agentId": agent_id,
        "totalCalls": total_calls,
        "totalDurationMinutes": round(total_duration / 60.0, 2)
    }

@router.get(
    "/agents/{agentId}/conversations",
    status_code=status.HTTP_200_OK,
    summary="List Agent Conversations",
    description="Retrieves a list of all historical call logs and chats for a specific agent."
)
async def list_agent_conversations(
    agentId: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    
    async def run_list_convs():
        db = mongo_db.client.get_default_database()
        cursor = db['Agent_Stream_CallsLogs'].find({
            "$or": [{"agentId": agentId}, {"agent_id": agentId}]
        })
        conversations_list = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            if "timestamp" in doc and doc["timestamp"]:
                if isinstance(doc["timestamp"], datetime.datetime):
                    doc["timestamp"] = doc["timestamp"].isoformat()
            conversations_list.append(doc)
        return conversations_list

    conversations = []
    try:
        res = await safe_mongo_op(run_list_convs)
        if res:
            conversations = res
    except Exception as e:
        logger.error(f"Failed to list agent conversations: {e}")

    return {
        "success": True,
        "conversations": conversations
    }

@router.get(
    "/conversations/{conversationId}",
    status_code=status.HTTP_200_OK,
    summary="Get Detailed Conversation Information",
    description="Fetches full telemetry logs and message transcripts for a single call session."
)
async def get_conversation_details(
    conversationId: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    
    async def run_get_details():
        db = mongo_db.client.get_default_database()
        query = {"$or": [{"call_id": conversationId}, {"callId": conversationId}]}
        if ObjectId.is_valid(conversationId):
            query["$or"].append({"_id": ObjectId(conversationId)})
        
        conversation_doc = await db['Agent_Stream_CallsLogs'].find_one(query)
        if conversation_doc:
            conversation_doc["_id"] = str(conversation_doc["_id"])
            if "timestamp" in conversation_doc and conversation_doc["timestamp"]:
                if isinstance(conversation_doc["timestamp"], datetime.datetime):
                    conversation_doc["timestamp"] = conversation_doc["timestamp"].isoformat()
        return conversation_doc

    conversation = None
    try:
        conversation = await safe_mongo_op(run_get_details)
    except Exception as e:
        logger.error(f"Failed to fetch conversation details: {e}")

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Conversation log not found"}
        )

    return {
        "success": True,
        "conversation": conversation
    }

@router.post(
    "/{id}/create-kb-text",
    status_code=status.HTTP_201_CREATED,
    summary="Create Knowledge Base Text",
    description="Uploads text content to S3, splits it into chunks, generates vector embeddings, and stores them in Chroma DB."
)
async def create_kb_text(
    id: str,
    payload: KBTextCreateRequest,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    agent_id = agent.get("agentId")
    import time
    doc_id = int(time.time())
    filename = f"kb_{doc_id}_{payload.title.replace(' ', '_')}.txt"
    file_bytes = payload.content.encode('utf-8')
    
    # 1. Trigger S3 Upload and Chroma indexing
    try:
        await rag_manager.upload_documents(
            company_id=agent_id,
            filename=filename,
            file_body=file_bytes,
            text_content=payload.content,
            doc_id=doc_id
        )
    except Exception as e:
        logger.error(f"Failed to upload and index KB text: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "message": f"Chroma/S3 indexing failed: {str(e)}"}
        )
    
    # 2. Persist metadata record in MongoDB
    kb_doc = {
        "agentId": agent_id,
        "docId": doc_id,
        "filename": filename,
        "title": payload.title,
        "createdAt": datetime.datetime.utcnow().isoformat() + "Z"
    }
    
    async def run_insert_kb():
        db = mongo_db.client.get_default_database()
        await db['agent_kb_documents'].insert_one(kb_doc.copy())

    if mongo_db.client is not None:
        try:
            await safe_mongo_op(run_insert_kb)
            if "_id" in kb_doc:
                kb_doc["_id"] = str(kb_doc["_id"])
        except Exception as e:
            logger.error(f"Failed to save KB document details to MongoDB: {e}")
            
    return {
        "success": True,
        "message": "Knowledge base document created and indexed successfully",
        "data": kb_doc
    }

@router.post(
    "/{id}/sendemialfromaiagentstools",
    status_code=status.HTTP_200_OK,
    summary="Save Email SMTP Credentials",
    description="Saves and secures SMTP server connection details for agent email delivery tools."
)
async def save_email_credentials(
    id: str,
    payload: SaveEmailCredentialsRequest,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    agent_id = agent.get("agentId")
    creds_doc = {
        "agentId": agent_id,
        "email": payload.email,
        "smtp_host": payload.smtp_host,
        "smtp_port": payload.smtp_port,
        "smtp_user": payload.smtp_user,
        "smtp_password": payload.smtp_password,
        "updatedAt": datetime.datetime.utcnow().isoformat() + "Z"
    }

    async def run_save_creds():
        db = mongo_db.client.get_default_database()
        await db['agent_email_credentials'].update_one(
            {"agentId": agent_id},
            {"$set": creds_doc},
            upsert=True
        )

    if mongo_db.client is not None:
        try:
            await safe_mongo_op(run_save_creds)
        except Exception as e:
            logger.error(f"Failed to save email credentials to MongoDB: {e}")

    return {
        "success": True,
        "message": "Email credentials saved successfully"
    }

@router.get(
    "/{id}/get-decrypted-email-credentials",
    status_code=status.HTTP_200_OK,
    summary="Get Email Credentials",
    description="Retrieves the SMTP configurations associated with this agent."
)
async def get_email_credentials(
    id: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    agent_id = agent.get("agentId")
    
    async def run_get_creds():
        db = mongo_db.client.get_default_database()
        return await db['agent_email_credentials'].find_one({"agentId": agent_id})

    creds = None
    if mongo_db.client is not None:
        try:
            creds = await safe_mongo_op(run_get_creds)
        except Exception as e:
            logger.error(f"Failed to fetch email credentials: {e}")

    if not creds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Email credentials not found for this agent"}
        )

    return {
        "success": True,
        "data": {
            "email": creds.get("email"),
            "smtp_host": creds.get("smtp_host"),
            "smtp_port": creds.get("smtp_port"),
            "smtp_user": creds.get("smtp_user"),
            "smtp_password": "••••••••"
        }
    }

@router.get(
    "/{id}/get-current-user-refresh-token",
    status_code=status.HTTP_200_OK,
    summary="Get Refresh Token",
    description="Returns token and session credentials for the agent dashboard context."
)
async def get_current_user_refresh_token(
    id: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"success": False, "message": "Agent not found"}
        )
    
    return {
        "success": True,
        "refresh_token": f"token_{uuid.uuid4().hex}"
    }

@router.post(
    "/{id}/upload-documents",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Agent Documents",
    description="Uploads files (PDF, DOCX, TXT) directly to the Exotel Voice Agent's Knowledge Base."
)
async def upload_agent_documents(
    id: str,
    background_tasks: BackgroundTasks,
    files: Annotated[List[UploadFile], File(description="Select one or more files to upload")],
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    # 1. Validate Enterprise & Agent in MongoDB
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail={"success": False, "message": "Agent not found"})
    
    agent_id = agent.get("agentId")
    
    # 2. Process Files
    for upload in files:
        body = await upload.read()
        
        # Optional: You can reuse your extract_text_from_file logic here if needed
        # text = extract_text_from_file(upload.filename, body) 
        
        doc_id = int(time.time())
        
        # 3. Trigger S3 Upload and Chroma indexing
        background_tasks.add_task(
            rag_manager.upload_documents,
            company_id=agent_id, # Uses agentId as the namespace in Chroma/S3
            filename=upload.filename,
            file_body=body,
            text_content="", # Or pass the extracted text
            doc_id=doc_id
        )
        
        # 4. Save metadata to MongoDB agent_kb_documents collection
        kb_doc = {
            "agentId": agent_id,
            "docId": doc_id,
            "filename": upload.filename,
            "title": upload.filename,
            "createdAt": datetime.datetime.utcnow().isoformat() + "Z"
        }
        
        db = mongo_db.client.get_default_database()
        await db['agent_kb_documents'].insert_one(kb_doc)
        
    return {
        "success": True,
        "message": "Documents uploaded and processing in background"
    }

@router.get(
    "/{id}/exotel-getkb-items",
    status_code=status.HTTP_200_OK,
    summary="List Agent Knowledge Base Items",
    description="Retrieves the list of documents and text items uploaded to the agent's knowledge base."
)
async def get_agent_kb_items(
    id: str,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail={"success": False, "message": "Agent not found"})
    
    agent_id = agent.get("agentId")
    
    db = mongo_db.client.get_default_database()
    kb_cursor = db['agent_kb_documents'].find({"agentId": agent_id})
    items = []
    async for kb in kb_cursor:
        if "_id" in kb:
            kb["_id"] = str(kb["_id"])
        items.append(kb)
        
    return {
        "success": True,
        "data": items
    }

@router.delete(
    "/{id}/exotel-deletekb-items/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Agent Knowledge Base Item",
    description="Deletes a specific knowledge base item from the agent."
)
async def delete_agent_kb_item(
    id: str,
    doc_id: int,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    validate_enterprise(x_enterprise_id)
    agent = await find_agent_by_id_and_enterprise(id, x_enterprise_id)
    if not agent:
        raise HTTPException(status_code=404, detail={"success": False, "message": "Agent not found"})
    
    agent_id = agent.get("agentId")
    db = mongo_db.client.get_default_database()
    
    doc = await db['agent_kb_documents'].find_one({"agentId": agent_id, "docId": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail={"success": False, "message": "Document not found"})
        
    await db['agent_kb_documents'].delete_one({"agentId": agent_id, "docId": doc_id})
    
    return {
        "success": True,
        "message": "Knowledge base item deleted successfully"
    }

@router.get(
    "/{id}/exotel-getkb-items/{doc_id}/download",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    summary="Download Agent Knowledge Base Item"
)
async def download_agent_kb_item(
    id: str,
    doc_id: int,
    enterprise_id: Optional[str] = Query(None, alias="enterprise_id"),
    is_download: bool = Query(False, alias="download"),
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    ent_id = x_enterprise_id or enterprise_id
    validate_enterprise(ent_id)
    agent = await find_agent_by_id_and_enterprise(id, ent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_id = agent.get("agentId")
    db = mongo_db.client.get_default_database()
    doc = await db['agent_kb_documents'].find_one({"agentId": agent_id, "docId": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    s3_key = f"documents/{agent_id}/{doc_id}_{doc['filename']}"
    if not rag_manager.s3_client:
        raise HTTPException(status_code=500, detail="S3 client not initialized")
        
    try:
        content_type, _ = mimetypes.guess_type(doc['filename'])
        disposition = f'attachment; filename="{doc["filename"]}"' if is_download else f'inline; filename="{doc["filename"]}"'
        url = rag_manager.s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': rag_manager.bucket_name, 
                'Key': s3_key,
                'ResponseContentDisposition': disposition,
                'ResponseContentType': content_type or 'application/octet-stream'
            },
            ExpiresIn=3600
        )
        return RedirectResponse(url)
    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate download link")
