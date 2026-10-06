#!/usr/bin/env python3
"""
WhatsApp API Client Service
Provides asynchronous, non-blocking WhatsApp text delivery via the configured
WhatsApp HTTP API (POST {"to": "<phone>", "message": "<text>"}).
Falls back to a mock log reporter when the API is not configured, mirroring
core/email_client.py's behaviour.
"""

import logging
from typing import Optional

import aiohttp

from config import Config

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Production WhatsApp API client with fallback logging."""

    @staticmethod
    def is_configured() -> bool:
        """Check if the WhatsApp API endpoint is configured."""
        return bool(Config.WHATSAPP_API_URL)

    @classmethod
    async def send_text(
        cls,
        recipient_phone: str,
        message: str,
        override: Optional[dict] = None,
    ) -> bool:
        """
        Send a WhatsApp text message asynchronously.

        override: optional per-agent config — {api_url, api_token} — reserved for
        future per-agent WhatsApp routing. When omitted, falls back to the global
        Config.WHATSAPP_* values.
        """
        recipient_phone = (recipient_phone or "").strip()
        if not recipient_phone:
            logger.warning("⚠️ WhatsApp skipped: Empty recipient phone number.")
            return False

        api_url = (override or {}).get("api_url") or Config.WHATSAPP_API_URL
        api_token = (override or {}).get("api_token") or Config.WHATSAPP_API_TOKEN

        # If not configured, fall back to mock log reporter
        if not api_url:
            logger.info(
                f"💬 [MOCK WHATSAPP CLIENT] To: {recipient_phone}\n"
                f"   Message: {message}\n"
                f"   👉 WHATSAPP_API_URL is missing. Mocking delivery."
            )
            return True

        headers = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        payload = {"to": recipient_phone, "message": message}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if 200 <= resp.status < 300:
                        logger.info(f"✅ WhatsApp message sent to {recipient_phone} (HTTP {resp.status})")
                        return True
                    error_data = await resp.text()
                    logger.error(f"❌ WhatsApp API error {resp.status}: {error_data}")
                    return False
        except Exception as e:
            logger.error(f"❌ Failed to send WhatsApp message to {recipient_phone}: {e}")
            return False
