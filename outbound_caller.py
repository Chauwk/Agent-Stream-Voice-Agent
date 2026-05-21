#!/usr/bin/env python3
"""
Outbound Call Maker - Trigger outbound calls from the SIP Server
Allows you to initiate callbacks to customers
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.openai_realtime_sales_bot import OpenAIRealtimeSalesBot

async def make_callback_call(phone_number: str, customer_name: str = "Customer"):
    """
    Make an outbound callback to a customer
    
    Args:
        phone_number: Customer phone number
        customer_name: Customer name for greeting
    """
    try:
        # Initialize bot
        bot = OpenAIRealtimeSalesBot()
        
        print(f"\n📱 Initiating outbound call...")
        print(f"📞 Target: {phone_number}")
        print(f"👤 Customer: {customer_name}")
        
        # Start SIP server in background
        sip_task = asyncio.create_task(bot._start_sip_server())
        
        # Give SIP server time to initialize
        await asyncio.sleep(3)
        
        # Make the outbound call
        if bot.sip_server:
            call_id = await bot.sip_server.make_outbound_call(
                phone_number=phone_number,
                context={
                    "customer_name": customer_name,
                    "greeting": f"Hi {customer_name}, this is Sarah calling from our sales team. How are you doing?"
                }
            )
            
            if call_id:
                print(f"\n✅ Call initiated successfully!")
                print(f"🆔 Call ID: {call_id}")
                print(f"⏱️  Call duration: check logs for details")
                
                # Keep the call running
                await asyncio.sleep(120)  # Run for 2 minutes
            else:
                print(f"\n❌ Failed to initiate call")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        print("\n👋 Ending call")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Make outbound calls via SIP")
    parser.add_argument("phone", help="Phone number to call (e.g., +919876543210)")
    parser.add_argument("--name", default="Customer", help="Customer name")
    
    args = parser.parse_args()
    
    print("🚀 Outbound Call Initiator")
    print("=" * 50)
    print(f"🌐 Mode: {('SIP Trunking' if Config.USE_SIP_TRUNK else 'WebSocket')}")
    print(f"📤 Outbound: {'✅ ENABLED' if Config.OUTBOUND_SIP_ENABLED else '❌ DISABLED'}")
    
    if not Config.OUTBOUND_SIP_ENABLED:
        print("\n⚠️  Outbound SIP is not enabled in .env")
        print("Set: OUTBOUND_SIP_ENABLED=true")
        sys.exit(1)
    
    if not Config.SIP_USERNAME or not Config.SIP_PASSWORD:
        print("\n⚠️  SIP credentials not configured")
        print("Set SIP_USERNAME and SIP_PASSWORD in .env")
        sys.exit(1)
    
    asyncio.run(make_callback_call(args.phone, args.name))
