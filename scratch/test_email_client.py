import asyncio
import sys
import os

# Inject project root path to allow correct import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from core.email_client import SMTPClient

async def run_tests():
    print("🧪 Running SMTPClient Verification Tests inside Container...")
    
    # 1. Test is_configured() when values are blank
    print("\n--- Test 1: Configured Check (Blank) ---")
    Config.SMTP_HOST = ""
    Config.SMTP_USER = ""
    Config.SMTP_PASSWORD = ""
    print(f"Is Configured: {SMTPClient.is_configured()} (Expected: False)")
    
    # 2. Test mock send_email fallback
    print("\n--- Test 2: Send Email (Mock Fallback Mode) ---")
    success = await SMTPClient.send_email(
        recipient_email="customer@example.com",
        subject="Welcome to Chauwk!",
        body="This is a test email body inside mock mode.",
        cc_recipient="partner@example.com"
    )
    print(f"Send Success: {success} (Expected: True)")
    
    # 3. Test is_configured() when values are populated
    print("\n--- Test 3: Configured Check (Populated) ---")
    Config.SMTP_HOST = "smtp.test.com"
    Config.SMTP_USER = "testuser"
    Config.SMTP_PASSWORD = "testpassword"
    print(f"Is Configured: {SMTPClient.is_configured()} (Expected: True)")

if __name__ == "__main__":
    asyncio.run(run_tests())
