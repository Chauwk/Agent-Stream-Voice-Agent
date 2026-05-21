#!/usr/bin/env python3
"""
Voice AI Bot - Simple Entry Point with Mode Selection
Supports both WebSocket (Exotel Applet) and SIP Trunk modes
"""

import asyncio
import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.openai_realtime_sales_bot import main as bot_main

def main():
    """Main entry point"""
    print('🚀 Voice AI Bot')
    print('=' * 50)
    
    # Validate configuration
    try:
        Config.validate()
        print('✅ Configuration valid')
        print(f'🏢 Company: {Config.COMPANY_NAME}')
        print(f'🤖 Bot: {Config.SALES_BOT_NAME}')
        
        # Display mode
        if Config.USE_SIP_TRUNK:
            print('📡 Mode: Direct SIP Trunking (cost-effective)')
            print(f'🔌 SIP Server: {Config.SIP_SERVER_HOST}:{Config.SIP_SERVER_PORT}')
            print(f'🌐 Public IP: {Config.SIP_PUBLIC_IP}')
            print(f'🔐 Authentication: IP-based (Exotel vSIP - no credentials needed)')
        else:
            print('📡 Mode: WebSocket + Exotel Voicebot Applet')
            print(f'🔌 WebSocket: {Config.SERVER_HOST}:{Config.SERVER_PORT}')
        
    except ValueError as e:
        print(f'❌ Configuration error: {e}')
        print('💡 Edit .env file with your settings')
        sys.exit(1)
    
    # Start the bot
    try:
        print()
        print('🤖 Starting bot...')
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        print()
        print('👋 Bot stopped')
    except ImportError as e:
        if 'pjsua' in str(e) or 'SIP' in str(e):
            print()
            print(f'❌ Error: {e}')
            print()
            print('💡 For SIP Trunk mode, install SIP libraries:')
            print('   pip install pjsua2-py PyAudio')
            print()
            print('💡 Or switch to WebSocket mode by setting:')
            print('   USE_SIP_TRUNK=false')
        else:
            print(f'❌ Error: {e}')
        sys.exit(1)
    except Exception as e:
        print()
        print(f'❌ Error: {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()

