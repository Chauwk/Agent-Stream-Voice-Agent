#!/usr/bin/env python3
"""
Controller: Call Controller
Handles the functional business logic for outbound calling, call status checks, and callback handlers.
"""

import logging
from typing import Dict, Any, Optional
from config import Config
from core.exotel_outbound_api import ExotelOutboundAPI

logger = logging.getLogger(__name__)

# Cache store for local call tracking (simulating persistent logging or database storage)
_call_records_cache: Dict[str, Dict[str, Any]] = {}

async def initiate_outbound_call(phone_number: str, customer_name: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Functional logic to initiate an outbound call via Exotel's REST API.
    
    Args:
        phone_number: Customer phone number in E.164 format.
        customer_name: Customer's name.
        context: Optional custom metadata dictionary associated with the call (e.g. lead source, campaign).
        
    Returns:
        Dict detailing success state, call SID, and metadata.
    """
    logger.info(f"📞 [CallController] Triggering outbound call: {phone_number} ({customer_name})")
    
    try:
        # Create standard Exotel greeting message using custom greeting template
        greeting = f"Hi {customer_name}, this is {Config.SALES_BOT_NAME} from our sales team. Please wait while I connect you."
        
        # Initialize the API client
        api = ExotelOutboundAPI()
        
        # Call the actual underlying integration method
        call_sid = await api.make_outbound_call(
            phone_number=phone_number,
            greeting_text=greeting,
            context={
                "customer_name": customer_name,
                "purpose": "sales_callback",
                **(context or {})
            }
        )
        
        if not call_sid:
            logger.error(f"❌ [CallController] Telephony client failed to initiate call to {phone_number}")
            return {
                "success": False,
                "error": "Telephony outbound call failed to initiate. Please verify Exotel configurations."
            }
            
        logger.info(f"✅ [CallController] Call successfully initiated. SID: {call_sid}")
        
        # Save details inside local memory cache record for telemetry tracking
        import time
        record = {
            "call_sid": call_sid,
            "phone_number": phone_number,
            "customer_name": customer_name,
            "status": "initiated",
            "context": context or {},
            "timestamp": time.time(),
            "error": None
        }
        _call_records_cache[call_sid] = record
        
        # Save to MongoDB outbound_calls collection
        try:
            from core.mongo_manager import mongo_db
            if mongo_db.client is not None:
                db = mongo_db.client.get_default_database()
                await db['outbound_calls'].insert_one(record.copy())
                logger.info(f"💾 Persisted outbound call record to MongoDB for phone: {phone_number}")
        except Exception as db_err:
            logger.error(f"⚠️ Failed to persist outbound call record to MongoDB: {db_err}")
        
        return {
            "success": True,
            "call_sid": call_sid,
            "status": "initiated",
            "message": "Outbound call request queued and initiated successfully."
        }
        
    except Exception as e:
        logger.error(f"❌ [CallController] Critical exception during call initiation: {e}")
        return {
            "success": False,
            "error": f"Internal Server Error: {str(e)}"
        }

async def fetch_call_status(call_sid: str) -> Dict[str, Any]:
    """
    Functional logic to query the active status of a call from Exotel API.
    
    Args:
        call_sid: The unique Exotel Call identifier.
        
    Returns:
        Dict with call status metadata.
    """
    logger.info(f"🔍 [CallController] Querying status for Call SID: {call_sid}")
    
    try:
        api = ExotelOutboundAPI()
        status_info = await api.get_call_status(call_sid)
        
        if not status_info:
            logger.warning(f"⚠️ [CallController] Status not found for Call SID: {call_sid}")
            
            # Check cache fallback
            if call_sid in _call_records_cache:
                return {
                    "success": True,
                    "call_sid": call_sid,
                    "status": _call_records_cache[call_sid]["status"],
                    "note": "Telephony service offline or key invalid. Details loaded from local cache records."
                }
                
            return {
                "success": False,
                "error": f"Call SID '{call_sid}' could not be retrieved from Telephony Service or local records."
            }
            
        # Update local cache record
        if call_sid not in _call_records_cache:
            _call_records_cache[call_sid] = {
                "call_sid": call_sid,
                "phone_number": status_info.get("To"),
                "customer_name": "Unknown",
                "context": {}
            }
        
        _call_records_cache[call_sid]["status"] = status_info.get("Status", "unknown")
        
        # Update status in MongoDB outbound_calls collection
        try:
            from core.mongo_manager import mongo_db
            if mongo_db.client is not None:
                db = mongo_db.client.get_default_database()
                await db['outbound_calls'].update_one(
                    {"call_sid": call_sid},
                    {"$set": {
                        "status": status_info.get("Status", "unknown"),
                        "duration": status_info.get("Duration")
                    }}
                )
                logger.info(f"💾 Updated outbound call status in MongoDB via fetch query for SID: {call_sid}")
        except Exception as db_err:
            logger.error(f"⚠️ Failed to update outbound call status in MongoDB via fetch: {db_err}")
        
        return {
            "success": True,
            "call_sid": call_sid,
            "status": status_info.get("Status"),
            "duration": status_info.get("Duration"),
            "direction": status_info.get("Direction", "outbound"),
            "from_number": status_info.get("From"),
            "to_number": status_info.get("To"),
            "start_time": status_info.get("StartTime"),
            "price": status_info.get("Price")
        }
        
    except Exception as e:
        logger.error(f"❌ [CallController] Exception fetching call status: {e}")
        return {
            "success": False,
            "error": f"Internal Server Error: {str(e)}"
        }

async def process_telephony_webhook(webhook_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Functional logic to process incoming webhook events from the telephony system (e.g. call.completed).
    
    Args:
        webhook_payload: Raw event dictionary from Exotel callbacks.
        
    Returns:
        Dict confirming processing outcomes.
    """
    call_sid = webhook_payload.get("CallSid") or webhook_payload.get("call_sid")
    event_type = webhook_payload.get("EventType") or webhook_payload.get("event")
    
    logger.info(f"📥 [CallController] Telephony Webhook Received: Event={event_type}, CallSID={call_sid}")
    
    if not call_sid:
        return {
            "success": False,
            "error": "Missing CallSid identifier in callback payload."
        }
        
    # Update state cache records
    if call_sid in _call_records_cache:
        _call_records_cache[call_sid]["status"] = event_type or "completed"
        if "duration" in webhook_payload:
            _call_records_cache[call_sid]["duration"] = webhook_payload.get("duration")
            
    # Update status in MongoDB outbound_calls collection
    try:
        from core.mongo_manager import mongo_db
        if mongo_db.client is not None:
            db = mongo_db.client.get_default_database()
            await db['outbound_calls'].update_one(
                {"call_sid": call_sid},
                {"$set": {
                    "status": event_type or "completed",
                    "duration": webhook_payload.get("duration")
                }}
            )
            logger.info(f"💾 Updated outbound call status in MongoDB for SID: {call_sid}")
    except Exception as db_err:
        logger.error(f"⚠️ Failed to update outbound call status in MongoDB: {db_err}")
            
    return {
        "success": True,
        "call_sid": call_sid,
        "processed_event": event_type,
        "message": "Callback event successfully audited and integrated."
    }
