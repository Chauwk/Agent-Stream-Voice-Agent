import logging
import json
import datetime
import asyncio
import time
from config import Config
from core.mongo_manager import mongo_db

logger = logging.getLogger(__name__)

async def extract_call_analytics(transcript_list: list) -> dict:
    """Uses Gemini to analyze the transcript and extract structured analytics fields."""
    # Convert transcript to text block
    formatted_transcript = ""
    for turn in transcript_list:
        role = turn.get("role", "user").upper()
        msg = turn.get("msg", "")
        formatted_transcript += f"{role}: {msg}\n"
        
    prompt = f"""
Analyze the following telephone conversation transcript between an AI sales agent (BOT) and a customer (USER).
Extract the following structured fields in JSON format:
1. "name": The name of the customer/caller (or "Not provided" if not found).
2. "address": The physical address or location details of the customer/caller (or "Not provided" if not found).
3. "email_id": The email address of the customer/caller (or "Not provided" if not found).
4. "caller_meeting_consent": "Yes" if the customer agreed to schedule a follow-up meeting/call, otherwise "No".
5. "customer_request_raised_field_visit": "Yes" if the customer explicitly requested a physical field visit or site visit, otherwise "No".
6. "business_interest": The category, product, or service the customer showed interest in (or "Not provided" if not found).
7. "call_summary": A concise 2-3 sentence summary of the key discussion points and outcome.

Return ONLY a valid JSON object matching the keys above. Do not include markdown code block formatting or backticks.

Transcript:
{formatted_transcript}
"""
    try:
        import google.genai as genai
        from google.genai import types
        # Initialize client
        client = genai.Client()
        response = await client.aio.models.generate_content(
            model=Config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        content_text = response.text.strip()
        # Clean potential markdown output from Gemini if response_mime_type is not honored
        if content_text.startswith("```"):
            if "json" in content_text:
                content_text = content_text.split("json")[1]
            else:
                content_text = content_text.split("```")[1]
            content_text = content_text.split("```")[0].strip()
            
        data = json.loads(content_text)
        # Validate keys
        keys = ["name", "address", "email_id", "caller_meeting_consent", 
                "customer_request_raised_field_visit", "business_interest", "call_summary"]
        for k in keys:
            if k not in data:
                data[k] = "Not provided" if k not in ["caller_meeting_consent", "customer_request_raised_field_visit"] else "No"
        return data
    except Exception as e:
        logger.error(f"Failed to extract call analytics via Gemini: {e}")
        return {
            "name": "Not provided",
            "address": "Not provided",
            "email_id": "Not provided",
            "caller_meeting_consent": "No",
            "customer_request_raised_field_visit": "No",
            "business_interest": "Not provided",
            "call_summary": "Failed to analyze transcript"
        }

async def save_enriched_call_log(call_id: str, duration: float, transcript: list, to_phone: str, direction: str):
    """Enriches transcript using Gemini and saves the complete call analytics document to MongoDB."""
    try:
        logger.info(f"🧠 Generating Gemini analytics extraction for call {call_id}...")
        analytics = await extract_call_analytics(transcript)
        
        now = datetime.datetime.utcnow()
        # Format date and time fields for the analytics tables
        call_date = now.strftime("%Y-%m-%d")
        call_time = now.strftime("%I:%M %p")
        
        call_log = {
            "call_id": call_id,
            "call_date": call_date,
            "time": call_time,
            "duration_seconds": round(duration, 2),
            "duration": f"{round(duration, 2)}s",
            "agent_name": Config.SALES_BOT_NAME,
            "company_name": Config.COMPANY_NAME,
            "caller_phone_no": to_phone,
            "lead_phone_no": to_phone if to_phone != "default" else "Web Caller",
            "timestamp": now,
            
            # Transcript and summary
            "transcript": transcript,
            "messages_count": len(transcript),
            
            # Extracted Fields from Gemini
            "name": analytics.get("name", "Not provided"),
            "address": analytics.get("address", "Not provided"),
            "email_id": analytics.get("email_id", "Not provided"),
            "caller_meeting_consent": analytics.get("caller_meeting_consent", "No"),
            "customer_request_raised_field_visit": analytics.get("customer_request_raised_field_visit", "No"),
            "business_interest": analytics.get("business_interest", "Not provided"),
            "call_summary": analytics.get("call_summary", "Not provided")
        }
        
        await mongo_db.save_call_log(call_log)
    except Exception as e:
        logger.error(f"❌ Error generating or saving enriched call log: {e}")
