import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from core.email_client import SMTPClient

async def main():
    print("SMTP_HOST:", Config.SMTP_HOST)
    print("SMTP_USER:", Config.SMTP_USER)
    print("Is Configured:", SMTPClient.is_configured())
    
    print("\nSending live test email to hello@chauwk.com...")
    res = await SMTPClient.send_email(
        recipient_email="hello@chauwk.com",
        subject="Test Zoho SMTP Connection",
        body="This is a real test email sent to verify Zoho SMTP credentials configured for the bot."
    )
    print("Email Send Result:", res)

if __name__ == "__main__":
    asyncio.run(main())
