#!/usr/bin/env python3
"""
Exotel Outbound Call REST API Integration
Makes outbound calls via Exotel's REST API (simpler than SIP outbound)

Flow:
1. Your code calls make_outbound_call()
2. We POST to Exotel REST API with customer number
3. Exotel dials the customer
4. Customer answers
5. Exotel routes call back to your inbound vSIP (port 5060)
6. Your bot answers and converses (existing inbound flow)
"""

import asyncio
import logging
import aiohttp
import json
from typing import Dict, Any, Optional
from config import Config

logger = logging.getLogger(__name__)

class ExotelOutboundAPI:
    """Handle outbound calls via Exotel REST API"""
    
    def __init__(self):
        """Initialize Exotel API client"""
        # Get from Exotel dashboard
        self.api_token = Config.EXOTEL_API_TOKEN
        self.account_sid = Config.EXOTEL_ACCOUNT_SID
        self.exotel_number = Config.EXOTEL_FROM_NUMBER  # Your virtual number
        self.api_base_url = "https://api.exotel.com/v1"
        
        logger.info("🔌 Exotel Outbound API initialized")
        logger.info(f"📞 From Number: {self.exotel_number}")
    
    async def make_outbound_call(
        self,
        phone_number: str,
        greeting_text: str = None,
        context: Dict[str, Any] = None
    ) -> Optional[str]:
        """
        Make an outbound call to a customer
        
        Args:
            phone_number: Customer phone number (e.g., "+919876543210")
            greeting_text: (Optional) Initial greeting text
            context: (Optional) Context data for the call
            
        Returns:
            call_sid: Exotel call ID, or None if failed
            
        Example:
            call_sid = await api.make_outbound_call(
                "+919876543210",
                greeting_text="Hi John, this is Sarah calling..."
            )
        """
        try:
            # Format phone number
            if not phone_number.startswith("+"):
                phone_number = "+" + phone_number
            
            logger.info(f"📤 Making outbound call to {phone_number}")
            
            # Prepare API request
            url = f"{self.api_base_url}/Accounts/{self.account_sid}/Calls"
            
            payload = {
                "to": phone_number,
                "from": self.exotel_number,
                # After customer answers, route to your inbound vSIP
                "CallbackUrl": f"http://{Config.SIP_PUBLIC_IP}:5060",
                "CallbackMethod": "POST",
                # Optional: greeting message (TTS)
                "FirstPartyPlay": greeting_text or "Please wait while we connect your call"
            }
            
            if context:
                payload["CustomData"] = json.dumps(context)
            
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            # Make API call
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200 or resp.status == 201:
                        data = await resp.json()
                        call_sid = data.get("Call", {}).get("Sid")
                        
                        logger.info(f"✅ Outbound call created")
                        logger.info(f"📞 Target: {phone_number}")
                        logger.info(f"🆔 Call SID: {call_sid}")
                        logger.info(f"📊 Status: {data.get('Call', {}).get('Status')}")
                        
                        return call_sid
                    else:
                        error_data = await resp.text()
                        logger.error(f"❌ Exotel API error: {resp.status}")
                        logger.error(f"Response: {error_data}")
                        return None
        
        except Exception as e:
            logger.error(f"❌ Error making outbound call: {e}")
            return None
    
    async def get_call_status(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of an outbound call
        
        Args:
            call_sid: Exotel call ID
            
        Returns:
            Call status info or None if failed
        """
        try:
            url = f"{self.api_base_url}/Accounts/{self.account_sid}/Calls/{call_sid}"
            
            headers = {
                "Authorization": f"Bearer {self.api_token}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        call_info = data.get("Call", {})
                        
                        logger.info(f"📊 Call {call_sid} status: {call_info.get('Status')}")
                        return call_info
                    else:
                        logger.error(f"❌ Failed to get call status: {resp.status}")
                        return None
        
        except Exception as e:
            logger.error(f"❌ Error getting call status: {e}")
            return None
    
    async def hangup_call(self, call_sid: str) -> bool:
        """
        Hang up an active call
        
        Args:
            call_sid: Exotel call ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.api_base_url}/Accounts/{self.account_sid}/Calls/{call_sid}"
            
            payload = {
                "Action": "hangup"
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Call {call_sid} hung up")
                        return True
                    else:
                        logger.error(f"❌ Failed to hangup: {resp.status}")
                        return False
        
        except Exception as e:
            logger.error(f"❌ Error hanging up call: {e}")
            return False


# Simple async client for testing
async def test_outbound_call():
    """Test making an outbound call"""
    api = ExotelOutboundAPI()
    
    call_sid = await api.make_outbound_call(
        "+919876543210",
        greeting_text="Hi John, this is Sarah from our sales team. Please wait..."
    )
    
    if call_sid:
        print(f"✅ Call initiated: {call_sid}")
        
        # Wait and check status
        await asyncio.sleep(5)
        status = await api.get_call_status(call_sid)
        print(f"📊 Status: {status}")
        
        # Hang up after 10 seconds
        await asyncio.sleep(5)
        await api.hangup_call(call_sid)
    else:
        print("❌ Failed to make call")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_outbound_call())
