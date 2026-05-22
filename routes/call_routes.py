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
    success: bool = Field(..., example=True)
    call_sid: Optional[str] = Field(None, example="ex_call_8e90810557fc4dc4ab5c04")
    status: Optional[str] = Field(None, example="initiated")
    message: Optional[str] = Field(None, example="Outbound call request initiated successfully.")
    error: Optional[str] = Field(None, example=None)

class CallStatusDetailsResponse(BaseModel):
    success: bool = Field(..., example=True)
    call_sid: str = Field(..., example="ex_call_8e90810557fc4dc4ab5c04")
    status: str = Field(..., example="completed")
    duration: Optional[int] = Field(45, example=45)
    direction: str = Field("outbound", example="outbound")
    from_number: Optional[str] = Field(None, example="+918047190000")
    to_number: Optional[str] = Field(None, example="+919876543210")
    start_time: Optional[str] = Field(None, example="2026-05-22 10:17:41")
    price: Optional[str] = Field(None, example="0.50")
    error: Optional[str] = Field(None, example=None)

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

@router.post(
    "/webhook",
    summary="Telephony Callback Handler",
    description="Receive callbacks from Exotel gateways to audit call lifecycle (ringing, answers, timeouts, disconnects)."
)
async def call_webhook(payload: WebhookCallbackPayload):
    """Register incoming webhooks from carrier callback nodes."""
    result = await call_controller.process_telephony_webhook(payload.dict())
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error")
        )
        
    return result
