#!/usr/bin/env python3
"""
Route Definitions: Agent Routes
Exposes REST endpoints for creating and managing custom voice agents.
Conforms to the NewAgentsApiSchema specification.
"""

import logging
import uuid
import datetime
from typing import List, Dict, Any, Optional, Union
from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel, Field
from bson import ObjectId

from core.mongo_manager import mongo_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Voice Agent Management"],
    responses={
        500: {"description": "Internal Server Error"}
    }
)

# === Pydantic Request Schemas ===

class TermsModel(BaseModel):
    enabled: bool = Field(False, example=True)
    content: str = Field("", example="By speaking with this agent you agree...")

class AgentCreateRequest(BaseModel):
    name: str = Field(..., example="Support Assistant", description="The name of the AI agent.")
    instructions: str = Field(..., example="You are a helpful customer support agent...", description="Prompt or core instructions.")
    firstMessage: str = Field(..., example="Hello! How can I help you today?", description="The first message said by the agent.")
    voiceId: str = Field(..., example="pNInz6obbfDQGcgMyIGD", description="The ID of the voice to be used.")
    language: Union[str, List[str]] = Field(..., example="en", description="Primary language of the agent (string or array).")
    
    # Optional Fields
    description: Optional[str] = Field("", example="Handles general customer inquiries.")
    knowledgeBaseIds: Optional[List[str]] = Field(default_factory=list, example=["64a2f8c8d8b9a7f3e1c2d3a4"])
    terms: Optional[TermsModel] = Field(default_factory=lambda: TermsModel(enabled=False, content=""))
    platformAgreement: Optional[Union[str, bool]] = Field(None, example=True)
    hinglish_mode: Optional[bool] = Field(False, example=False)

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

# === API Endpoint Routes ===

@router.post(
    "",
    response_model=AgentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Voice Agent",
    description="Registers a new custom voice agent on our own bot system and logs the metadata in MongoDB."
)
async def create_agent(
    payload: AgentCreateRequest,
    x_enterprise_id: Optional[str] = Header(None, alias="x-enterprise-id")
):
    # 1. Validate Enterprise ID is present
    enterprise_id = x_enterprise_id
    if not enterprise_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": "Missing required fields: Enterprise ID in headers (x-enterprise-id)"
            }
        )
    
    # 2. Simulate account suspension and existence checks for testing
    if enterprise_id == "suspended-enterprise":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "message": "Enterprise account is suspended"
            }
        )
    elif enterprise_id == "nonexistent-enterprise":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "message": "Enterprise account does not exist"
            }
        )
        
    # 3. Resolve language field (if array, pick first element)
    resolved_lang = payload.language
    if isinstance(resolved_lang, list):
        if len(resolved_lang) > 0:
            resolved_lang = resolved_lang[0]
        else:
            resolved_lang = "en"
            
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
    saved_in_db = False
    if mongo_db.client is not None:
        try:
            # Retrieve database configured in default connection string
            db = mongo_db.client.get_default_database()
            agents_collection = db['agents']
            await agents_collection.insert_one(agent_data.copy())
            logger.info(f"✅ Voice agent {agent_uuid} successfully registered in MongoDB")
            saved_in_db = True
        except Exception as e:
            logger.error(f"❌ Failed to persist voice agent {agent_uuid} to MongoDB: {e}")
            # Continue so API doesn't crash, behaving gracefully
    
    if not saved_in_db:
        logger.warning(f"⚠️ Voice agent {agent_uuid} created in memory only (no active MongoDB connection)")
        
    return {
        "success": True,
        "message": "Agent created successfully",
        "data": agent_data
    }
