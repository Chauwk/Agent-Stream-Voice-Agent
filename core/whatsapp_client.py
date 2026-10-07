#!/usr/bin/env python3
"""
WhatsApp API Client Service
Provides asynchronous, non-blocking WhatsApp text delivery via the configured
WhatsApp HTTP API (POST {"to": "<phone>", "message": "<text>"}).
Falls back to a mock log reporter when the API is not configured, mirroring
core/email_client.py's behaviour.

send_text returns a detail dict so callers can log exactly what happened:
    {
        "success":  bool,          # True only on a real 2xx (or mock)
        "called":   bool,          # False when mock mode (no API call made)
        "status":   int | None,    # HTTP status code, or None (mock/exception)
        "response": str,           # response body / mock note / exception text
        "api_url":  str | None,    # the endpoint actually hit
    }
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
    ) -> dict:
        """
        Send a WhatsApp text message asynchronously.

        override: optional per-agent config — {api_url, api_token} — reserved for
        future per-agent WhatsApp routing. When omitted, falls back to the global
        Config.WHATSAPP_* values.

        Returns a detail dict (see module docstring) — never raises.
        """
        recipient_phone = (recipient_phone or "").strip()
        if not recipient_phone:
            logger.warning("⚠️ WhatsApp skipped: Empty recipient phone number.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty recipient phone number.", "api_url": None}

        api_url = (override or {}).get("api_url") or Config.WHATSAPP_API_URL
        api_token = (override or {}).get("api_token") or Config.WHATSAPP_API_TOKEN

        # If not configured, fall back to mock log reporter (no API call made).
        if not api_url:
            logger.info(
                f"💬 [MOCK WHATSAPP CLIENT] To: {recipient_phone}\n"
                f"   Message: {message}\n"
                f"   👉 WHATSAPP_API_URL is missing. Mocking delivery."
            )
            return {"success": True, "called": False, "status": None,
                    "response": "MOCK: WHATSAPP_API_URL not configured; no API call made.",
                    "api_url": None}

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
                    body = await resp.text()
                    ok = 200 <= resp.status < 300
                    if ok:
                        logger.info(f"✅ WhatsApp message sent to {recipient_phone} (HTTP {resp.status})")
                    else:
                        logger.error(f"❌ WhatsApp API error {resp.status}: {body}")
                    return {"success": ok, "called": True, "status": resp.status,
                            "response": (body or "")[:2000], "api_url": api_url}
        except Exception as e:
            logger.error(f"❌ Failed to send WhatsApp message to {recipient_phone}: {e}")
            return {"success": False, "called": True, "status": None,
                    "response": f"exception: {e}", "api_url": api_url}
