#!/usr/bin/env python3
"""
Route Definitions: Call Routes
Exposes REST endpoints for triggering calls, fetching status, and receiving callbacks.
Generates comprehensive OpenAPI Swagger schemas.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from controllers import call_controller

router = APIRouter(
    prefix="/api/v1/calls",
    tags=["Call Management"],
    responses={
        401: {"description": "Unauthorized Access - Bearer token missing or invalid"},
        500: {"description": "Internal Server Error"}
    }
)


# === Pydantic Input Schemas for Request Validation ===

class OutboundCallRequest(BaseModel):
    phone_number: str = Field(
        ..., 
        example="+919876543210", 
        description="Target phone number in international E.164 standard formatting."
    )
    customer_name: str = Field(
        "Customer", 
        example="John Doe", 
        description="Name of the customer being called to personalize synthesized greeting."
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        example={"campaign_id": "spring_promotion_2026", "source": "HubSpot"},
        description="Arbitrary dictionary context to trace conversation history and CRM updates."
    )

class WebhookCallbackPayload(BaseModel):
    CallSid: str = Field(..., example="ex_call_8e90810557fc4dc4ab5c04", description="Exotel Call identifier.")
    EventType: str = Field(..., example="call.completed", description="The nature of the callback event.")
    Duration: Optional[int] = Field(None, example=45, description="Call duration in seconds.")
    CustomData: Optional[str] = Field(None, description="Optional raw serialised context passed during trigger.")

# === Pydantic Output Schemas for Swagger Documentation ===

class CallActionResponse(BaseModel):
    success: bool = Field(..., json_schema_extra={"example": True})
    call_sid: Optional[str] = Field(None, json_schema_extra={"example": "ex_call_8e90810557fc4dc4ab5c04"})
    status: Optional[str] = Field(None, json_schema_extra={"example": "initiated"})
    message: Optional[str] = Field(None, json_schema_extra={"example": "Outbound call request initiated successfully."})
    error: Optional[str] = Field(None, json_schema_extra={"example": None})

class CallStatusDetailsResponse(BaseModel):
    success: bool = Field(..., json_schema_extra={"example": True})
    call_sid: str = Field(..., json_schema_extra={"example": "ex_call_8e90810557fc4dc4ab5c04"})
    status: str = Field(..., json_schema_extra={"example": "completed"})
    duration: Optional[int] = Field(45, json_schema_extra={"example": 45})
    direction: str = Field("outbound", json_schema_extra={"example": "outbound"})
    from_number: Optional[str] = Field(None, json_schema_extra={"example": "+918047190000"})
    to_number: Optional[str] = Field(None, json_schema_extra={"example": "+919876543210"})
    start_time: Optional[str] = Field(None, json_schema_extra={"example": "2026-05-22 10:17:41"})
    price: Optional[str] = Field(None, json_schema_extra={"example": "0.50"})
    error: Optional[str] = Field(None, json_schema_extra={"example": None})

# === API Endpoint Route Mappings ===

@router.post(
    "/outbound",
    response_model=CallActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Outbound Lead Call",
    description="Dial an outbound phone call via the Exotel gateway. PERSONALIZES greeting and prepares system to bridge call to low-latency AI conversation stream."
)
async def trigger_call(payload: OutboundCallRequest):
    """Trigger an outbound call using Exotel gateway REST API."""
    result = await call_controller.initiate_outbound_call(
        phone_number=payload.phone_number,
        customer_name=payload.customer_name,
        context=payload.context
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "An error occurred initiating outbound call")
        )
        
    return result

@router.get(
    "/status/{call_sid}",
    response_model=CallStatusDetailsResponse,
    summary="Retrieve Outbound Call Status",
    description="Inspect the real-time state, connection durations, billing costs, and outcomes of a call using the Exotel session SID."
)
async def get_status(call_sid: str):
    """Retrieve full Call details from telephony service."""
    result = await call_controller.fetch_call_status(call_sid)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("error", "Call SID not found or unavailable")
        )
        
    return result

from fastapi import Request

@router.post(
    "/webhook",
    summary="Telephony Callback Handler",
    description="Receive callbacks from Exotel gateways to audit call lifecycle (ringing, answers, timeouts, disconnects)."
)
async def call_webhook(request: Request):
    """Register incoming webhooks from carrier callback nodes."""
    content_type = request.headers.get("content-type", "")
    payload = {}
    if "application/x-www-form-urlencoded" in content_type:
        form_data = await request.form()
        payload = dict(form_data)
    else:
        try:
            payload = await request.json()
        except Exception:
            form_data = await request.form()
            payload = dict(form_data)
            
    logger.info(f"📥 Received Exotel webhook payload: {payload}")
    result = await call_controller.process_telephony_webhook(payload)
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error")
        )
        
    return result

# === New Endpoints for Dashboard Outbound Call Status & Batch Calling ===

import logging
import csv
import io
from fastapi import UploadFile, File

logger = logging.getLogger(__name__)

@router.get(
    "/outbound",
    summary="Get Outbound Call List",
    description="Retrieves a list of all outbound calls from MongoDB to display their status (initiated, ringing, completed, failed) in the admin panel."
)
async def get_outbound_calls():
    try:
        from core.mongo_manager import mongo_db
        if mongo_db.client is None:
            return {"success": True, "calls": []}
        db = mongo_db.client.get_default_database()
        cursor = db['outbound_calls'].find().sort("timestamp", -1)
        calls = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            calls.append(doc)
        return {"success": True, "calls": calls}
    except Exception as e:
        logger.error(f"Error fetching outbound calls: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}"
        )

@router.post(
    "/outbound/bulk",
    summary="Bulk Outbound Calls via CSV",
    description="Upload a CSV file containing phone_number and customer_name to initiate a batch of outbound calls."
)
async def trigger_bulk_calls(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    
    try:
        contents = await file.read()
        decoded = contents.decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(decoded))
        
        initiated_calls = []
        for row in csv_reader:
            phone = row.get("phone_number") or row.get("phone") or row.get("Phone Number") or row.get("phonenumber")
            name = row.get("customer_name") or row.get("name") or row.get("Customer Name") or row.get("customername") or "Customer"
            
            if not phone:
                continue
                
            phone = phone.strip()
            name = name.strip()
            
            # Call initiate_outbound_call controller function
            result = await call_controller.initiate_outbound_call(
                phone_number=phone,
                customer_name=name
            )
            initiated_calls.append({
                "phone_number": phone,
                "customer_name": name,
                "success": result.get("success", False),
                "call_sid": result.get("call_sid"),
                "error": result.get("error")
            })
            
        return {
            "success": True,
            "message": f"Successfully processed CSV file. Initiated {len(initiated_calls)} calls.",
            "details": initiated_calls
        }
    except Exception as e:
        logger.error(f"Error triggering bulk calls: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}"
        )
