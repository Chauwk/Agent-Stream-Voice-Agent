#!/usr/bin/env python3
"""
Test Script for Inbound Calls from Exotel
Supports both WebSocket (Voicebot Applet) and SIP Trunk modes

This script demonstrates how to:
1. Start the bot listening for inbound calls
2. Simulate an inbound call (for testing/development)
3. Monitor call status and logs
4. Perform load testing
"""

import asyncio
import websockets
import json
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InboundCallTester:
    """Test inbound call handling"""
    
    def __init__(self, host: str = 'localhost', port: int = 5000):
        self.host = host
        self.port = port
        self.ws_url = f"ws://{host}:{port}"
        
    async def simulate_websocket_inbound(self, phone_number: str = "+919876543210", 
                                        caller_name: str = "Test Caller", 
                                        duration_seconds: int = 10):
        """
        Simulate an inbound WebSocket call (Voicebot Applet mode)
        
        This mimics what Exotel sends when a customer calls your number.
        """
        print("\n" + "=" * 60)
        print("📞 Simulating Inbound WebSocket Call (Voicebot Applet)")
        print("=" * 60)
        print(f"🔗 URL: {self.ws_url}")
        print(f"📱 From: {phone_number}")
        print(f"👤 Caller: {caller_name}")
        print(f"⏱️  Duration: {duration_seconds}s")
        print()
        
        try:
            # Connect to the bot
            async with websockets.connect(self.ws_url) as websocket:
                logger.info(f"✅ Connected to bot at {self.ws_url}")
                
                # Send connection message (like Exotel does)
                init_msg = {
                    "event": "connected",
                    "from": phone_number,
                    "caller_name": caller_name,
                    "sample_rate": 24000,
                    "call_type": "inbound"
                }
                
                await websocket.send(json.dumps(init_msg))
                logger.info(f"📤 Sent: {init_msg}")
                
                # Simulate some audio data
                print("\n🎤 Simulating inbound audio for 10 seconds...")
                start_time = time.time()
                message_count = 0
                
                while time.time() - start_time < duration_seconds:
                    try:
                        # Try to receive responses from bot
                        try:
                            response = await asyncio.wait_for(
                                websocket.recv(), 
                                timeout=1.0
                            )
                            logger.info(f"📥 Bot response: {response[:100]}...")
                            
                            # Parse if JSON
                            try:
                                data = json.loads(response)
                                if data.get('event') == 'audio':
                                    message_count += 1
                                    logger.info(f"   🔊 Audio chunk #{message_count}")
                            except:
                                pass
                                
                        except asyncio.TimeoutError:
                            pass  # No message received, continue
                        
                        # Simulate sending audio every 100ms
                        await asyncio.sleep(0.1)
                        
                    except websockets.exceptions.ConnectionClosed:
                        logger.error("❌ Connection closed by bot")
                        break
                    except Exception as e:
                        logger.error(f"❌ Error: {e}")
                        break
                
                print(f"\n✅ Simulated call completed!")
                print(f"   Messages received: {message_count}")
                
        except ConnectionRefusedError:
            print(f"\n❌ Cannot connect to {self.ws_url}")
            print("   Make sure the bot is running:")
            print("   python main.py")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Error during simulation: {e}")
            sys.exit(1)
    
    async def test_connection(self) -> bool:
        """Test if bot is running and responding"""
        print("\n" + "=" * 60)
        print("🔍 Testing Bot Connection")
        print("=" * 60)
        
        try:
            async with websockets.connect(self.ws_url, timeout=5) as ws:
                logger.info(f"✅ Bot is running and responding at {self.ws_url}")
                return True
        except:
            logger.error(f"❌ Cannot reach bot at {self.ws_url}")
            print(f"\n💡 Start the bot with: python main.py")
            return False
    
    async def test_configuration(self):
        """Test if configuration is complete for inbound calls"""
        print("\n" + "=" * 60)
        print("⚙️  Checking Inbound Configuration")
        print("=" * 60)
        
        errors = []
        
        # Check OpenAI
        if not Config.OPENAI_API_KEY:
            errors.append("❌ OPENAI_API_KEY not set")
        else:
            print("✅ OpenAI API key configured")
        
        # Check company details
        if not Config.COMPANY_NAME:
            errors.append("❌ COMPANY_NAME not set")
        else:
            print(f"✅ Company: {Config.COMPANY_NAME}")
        
        # Check bot personality
        if not Config.SALES_BOT_NAME:
            errors.append("❌ SALES_BOT_NAME not set")
        else:
            print(f"✅ Bot Name: {Config.SALES_BOT_NAME}")
        
        # Check SIP configuration if SIP trunk mode
        if Config.USE_SIP_TRUNK:
            print("\n📡 SIP Trunk Mode:")
            if not Config.SIP_PUBLIC_IP:
                errors.append("❌ SIP_PUBLIC_IP not set (required for inbound SIP calls)")
            else:
                print(f"✅ Public IP: {Config.SIP_PUBLIC_IP}")
            
            print(f"✅ SIP Port: {Config.SIP_SERVER_PORT}")
        else:
            print("\n🌐 WebSocket Mode (Voicebot Applet):")
            print(f"✅ Server: {Config.SERVER_HOST}:{Config.SERVER_PORT}")
            print(f"✅ Bot Name: {Config.SALES_BOT_NAME}")
        
        if errors:
            print("\n" + "=" * 60)
            print("⚠️  Configuration Issues:")
            for error in errors:
                print(f"  {error}")
            print("\n💡 Edit .env file and restart the bot")
            return False
        else:
            print("\n✅ Configuration looks good!")
            return True


async def main():
    parser = argparse.ArgumentParser(
        description="Test inbound calls from Exotel"
    )
    
    parser.add_argument(
        'command',
        choices=['test-config', 'test-connection', 'simulate', 'quick-test'],
        help='Test command to run'
    )
    
    parser.add_argument(
        '--host',
        default='localhost',
        help='Bot host (default: localhost)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Bot port (default: 5000)'
    )
    
    parser.add_argument(
        '--phone',
        default='+919876543210',
        help='Phone number to simulate (default: +919876543210)'
    )
    
    parser.add_argument(
        '--name',
        default='Test Caller',
        help='Caller name (default: Test Caller)'
    )
    
    parser.add_argument(
        '--duration',
        type=int,
        default=10,
        help='Call duration in seconds (default: 10)'
    )
    
    args = parser.parse_args()
    
    tester = InboundCallTester(host=args.host, port=args.port)
    
    try:
        if args.command == 'test-config':
            await tester.test_configuration()
        
        elif args.command == 'test-connection':
            success = await tester.test_connection()
            sys.exit(0 if success else 1)
        
        elif args.command == 'simulate':
            success = await tester.test_connection()
            if success:
                await tester.simulate_websocket_inbound(
                    phone_number=args.phone,
                    caller_name=args.name,
                    duration_seconds=args.duration
                )
        
        elif args.command == 'quick-test':
            print("\n🚀 Running Quick Test Suite...")
            print("=" * 60)
            
            # Test 1: Check configuration
            config_ok = await tester.test_configuration()
            
            # Test 2: Check connection
            print()
            connection_ok = await tester.test_connection()
            
            # Test 3: Simulate a call
            if connection_ok:
                print()
                await tester.simulate_websocket_inbound(
                    phone_number='+919876543210',
                    caller_name='Quick Test Call',
                    duration_seconds=5
                )
            
            print("\n" + "=" * 60)
            print("✅ Quick test completed!")
    
    except KeyboardInterrupt:
        print("\n\n👋 Test interrupted")
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\n" + "=" * 60)
        print("📞 Inbound Call Testing for Exotel Bot")
        print("=" * 60)
        print("\nUsage: python test_inbound_calls.py <command> [options]")
        print("\nAvailable Commands:")
        print("  test-config      - Check configuration for inbound calls")
        print("  test-connection  - Test if bot is running")
        print("  simulate         - Simulate an inbound call")
        print("  quick-test       - Run all tests")
        print("\nExamples:")
        print("  # Test configuration")
        print("  python test_inbound_calls.py test-config")
        print("\n  # Test connection to bot")
        print("  python test_inbound_calls.py test-connection")
        print("\n  # Simulate inbound call")
        print("  python test_inbound_calls.py simulate --phone +919999999999")
        print("\n  # Run all tests")
        print("  python test_inbound_calls.py quick-test")
        print("\n" + "=" * 60)
        sys.exit(0)
    
    asyncio.run(main())
