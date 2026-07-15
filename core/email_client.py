#!/usr/bin/env python3
"""
SMTP Email Client Service
Provides asynchronous, non-blocking email transmission using standard Python smtplib.
Wraps blocking operations in asyncio.to_thread to maintain active voice/telephony concurrency.
Falls back to logging warning if SMTP credentials are not configured.
"""

import logging
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from config import Config

logger = logging.getLogger(__name__)

class SMTPClient:
    """Production SMTP Email Client with fallback logging"""
    
    @staticmethod
    def is_configured() -> bool:
        """Check if SMTP credentials are fully configured"""
        return bool(Config.SMTP_HOST and Config.SMTP_USER and Config.SMTP_PASSWORD)
        
    @classmethod
    async def send_email(
        cls,
        recipient_email: str,
        subject: str,
        body: str,
        cc_recipient: Optional[str] = None
    ) -> bool:
        """
        Send an email asynchronously in a background thread.
        """
        recipient_email = recipient_email.strip()
        if not recipient_email:
            logger.warning("⚠️ Email skipped: Empty recipient address.")
            return False

        # If not configured, fall back to mock log reporter
        if not cls.is_configured():
            cc_log = f" (CC: {cc_recipient})" if cc_recipient else ""
            logger.info(
                f"📧 [MOCK EMAIL CLIENT] To: {recipient_email}{cc_log}\n"
                f"   Subject: {subject}\n"
                f"   Body: {body}\n"
                f"   👉 SMTP details are missing in .env. Mocking delivery."
            )
            return True

        # Run the blocking send operation in a background thread
        return await asyncio.to_thread(
            cls._send_email_sync,
            recipient_email,
            subject,
            body,
            cc_recipient
        )

    @classmethod
    def _send_email_sync(
        cls,
        recipient_email: str,
        subject: str,
        body: str,
        cc_recipient: Optional[str] = None
    ) -> bool:
        """Synchronous SMTP email transmission helper"""
        try:
            # Create message container
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            
            # Setup sender
            from_name = Config.SMTP_FROM_NAME or "Chauwk Support"
            from_email = Config.SMTP_FROM_EMAIL or Config.SMTP_USER
            msg['From'] = f"{from_name} <{from_email}>"
            
            # Setup recipients
            msg['To'] = recipient_email
            recipients = [recipient_email]
            
            if cc_recipient:
                cc_recipient = cc_recipient.strip()
                msg['Cc'] = cc_recipient
                recipients.append(cc_recipient)

            # Record the MIME types of both parts - text/plain and text/html
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Setup SMTP server connection
            host = Config.SMTP_HOST
            port = Config.SMTP_PORT or 587
            username = Config.SMTP_USER
            password = Config.SMTP_PASSWORD

            logger.info(f"📧 Connecting to SMTP host {host}:{port}...")
            
            # Connect via SSL (port 465) or standard TLS (port 587)
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                server = smtplib.SMTP(host, port, timeout=10)
                server.ehlo()
                server.starttls()  # Upgrade connection to secure TLS
                server.ehlo()

            # Authenticate and send
            server.login(username, password)
            server.sendmail(from_email, recipients, msg.as_string())
            server.quit()
            
            cc_log = f" (CC: {cc_recipient})" if cc_recipient else ""
            logger.info(f"✅ Email successfully delivered to {recipient_email}{cc_log}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to deliver email to {recipient_email}: {e}", exc_info=True)
            return False
