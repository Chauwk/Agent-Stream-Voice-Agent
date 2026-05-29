#!/usr/bin/env python3
"""
Bot Validation Script - Check if bot is ready for testing
Run this before starting test calls
"""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Config

def check_dependencies():
    """Check if all required packages are installed"""
    print("\n🔍 Checking Dependencies...")
    print("-" * 50)
    
    required = {
        'openai': 'OpenAI API',
        'pjsua2': 'SIP library (pjsua2-py)',
        'pyaudio': 'Audio input/output',
        'dotenv': 'Environment variables',
        'numpy': 'Numerical computing',
        'pydub': 'Audio processing'
    }
    
    missing = []
    for pkg, desc in required.items():
        try:
            __import__(pkg)
            print(f"✅ {desc:30} ({pkg})")
        except ImportError:
            print(f"❌ {desc:30} ({pkg})")
            missing.append(pkg)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        # Map package names to pip install names
        install_map = {
            'pjsua2': 'pjsua2-py',
            'pyaudio': 'PyAudio',
            'pydub': 'pydub'
        }
        install_names = [install_map.get(pkg, pkg) for pkg in missing]
        print(f"   Run: pip install {' '.join(install_names)}")
        return False
    
    print("\n✅ All dependencies installed!")
    return True

def check_configuration():
    """Check if .env is properly configured"""
    print("\n🔍 Checking Configuration...")
    print("-" * 50)
    
    checks = {
        'OPENAI_API_KEY': 'OpenAI API Key',
        'EXOTEL_API_TOKEN': 'Exotel API Token',
        'EXOTEL_ACCOUNT_SID': 'Exotel Account SID',
        'EXOTEL_FROM_NUMBER': 'Exotel From Number',
        'COMPANY_NAME': 'Company Name',
        'SALES_BOT_NAME': 'Bot Name',
        'SIP_PUBLIC_IP': 'SIP Public IP'
    }
    
    missing = []
    for key, desc in checks.items():
        value = getattr(Config, key, None)
        if value:
            # Mask sensitive values
            if 'KEY' in key or 'TOKEN' in key:
                display = value[:10] + '...' if len(value) > 10 else value
            else:
                display = value
            print(f"✅ {desc:30} = {display}")
        else:
            print(f"❌ {desc:30} (NOT SET)")
            missing.append(key)
    
    if missing:
        print(f"\n⚠️  Missing configuration: {', '.join(missing)}")
        print(f"   Edit .env and set: {', '.join(missing)}")
        return False
    
    print("\n✅ Configuration complete!")
    return True

def check_openai_connection():
    """Test OpenAI API connection"""
    print("\n🔍 Checking OpenAI Connection...")
    print("-" * 50)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=Config.OPENAI_API_KEY)
        
        # Try a simple API call
        response = client.models.list()
        print(f"✅ OpenAI API connected!")
        print(f"   Available models: {len(response.data)}")
        print(f"   Using model: {Config.OPENAI_MODEL}")
        return True
    except Exception as e:
        print(f"❌ OpenAI connection failed: {e}")
        print(f"   Check OPENAI_API_KEY in .env")
        return False

def check_sip_configuration():
    """Verify SIP configuration"""
    print("\n🔍 Checking SIP Configuration...")
    print("-" * 50)
    
    checks = {
        'SIP_SERVER_HOST': ('SIP Host', '0.0.0.0'),
        'SIP_SERVER_PORT': ('SIP Port', 5060),
        'INBOUND_SIP_ENABLED': ('Inbound Enabled', True),
        'SIP_PUBLIC_IP': ('Public IP', 'Required')
    }
    
    all_ok = True
    for key, (desc, expected) in checks.items():
        value = getattr(Config, key, None)
        if value:
            if isinstance(expected, str) and expected == 'Required':
                print(f"✅ {desc:30} = {value}")
            else:
                match = str(value) == str(expected)
                status = "✅" if match else "⚠️"
                print(f"{status} {desc:30} = {value}")
        else:
            print(f"❌ {desc:30} (NOT SET)")
            all_ok = False
    
    if all_ok:
        print("\n✅ SIP configuration OK!")
    else:
        print("\n⚠️  Fix SIP configuration in .env")
    
    return all_ok

def main():
    """Run all checks"""
    print("\n" + "=" * 60)
    print("🤖 BOT VALIDATION - Testing Readiness Check")
    print("=" * 60)
    
    results = {
        'Dependencies': check_dependencies(),
        'Configuration': check_configuration(),
        'OpenAI Connection': check_openai_connection(),
        'SIP Configuration': check_sip_configuration()
    }
    
    print("\n" + "=" * 60)
    print("📋 VALIDATION SUMMARY")
    print("=" * 60)
    
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10} {check}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n" + "🎉 " * 15)
        print("✅ BOT IS READY FOR TESTING!")
        print("🎉 " * 15)
        print("\nNext steps:")
        print("1. Start the bot: python main.py")
        print("2. Wait for: 'Waiting for incoming SIP calls...'")
        print("3. Make test call to your Exotel virtual number")
        print("4. Check logs for 'Call state stored' message")
        print("\nSee bot-testing-plan.md for detailed test steps")
        return 0
    else:
        print("\n" + "⚠️ " * 15)
        print("❌ BOT NOT READY - Fix issues above first")
        print("⚠️ " * 15)
        return 1

if __name__ == '__main__':
    sys.exit(main())
