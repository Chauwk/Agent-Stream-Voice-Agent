#!/usr/bin/env python3
"""
WhatsApp API Client Service
Sends pre-approved WhatsApp **template** messages via the configured WhatsApp
HTTP API:
    POST {"to", "templateName", "languageCode", "components"?}
    200 -> {"success": true,  "messageId": "wamid..."}
    400 -> VALIDATION_ERROR
    502 -> WHATSAPP_API_ERROR  (Meta rejected it)

Falls back to a mock log reporter when the API is not configured, mirroring
core/email_client.py's behaviour.

send_template returns a detail dict so callers can log exactly what happened:
    {
        "success":    bool,          # HTTP 2xx AND body.success (if present)
        "called":     bool,          # False when mock mode (no API call made)
        "status":     int | None,    # HTTP status code, or None (mock/exception)
        "response":   str,           # response body / mock note / exception text
        "api_url":    str | None,    # the endpoint actually hit
        "message_id": str | None,    # wamid from the API response, if any
    }
"""

import json
import logging
from typing import Optional

import aiohttp

from config import Config

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Production WhatsApp template client with fallback logging."""

    @staticmethod
    def is_configured() -> bool:
        """Check if the WhatsApp API endpoint is configured."""
        return bool(Config.WHATSAPP_API_URL)

    @classmethod
    async def send_template(
        cls,
        recipient_phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[list] = None,
        override: Optional[dict] = None,
    ) -> dict:
        """
        Send a pre-approved WhatsApp template message asynchronously.

        components: optional Graph-API-shaped list, e.g.
            [{"type": "body", "parameters": [{"type": "text", "text": "Ganesh"}]}]
        override: optional per-agent config — {api_url, api_token}.

        Returns a detail dict (see module docstring) — never raises.
        """
        recipient_phone = (recipient_phone or "").strip()
        if not recipient_phone:
            logger.warning("⚠️ WhatsApp skipped: Empty recipient phone number.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty recipient phone number.", "api_url": None, "message_id": None}
        if not template_name:
            logger.warning("⚠️ WhatsApp skipped: Empty template name.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty template name.", "api_url": None, "message_id": None}

        api_url = (override or {}).get("api_url") or Config.WHATSAPP_API_URL
        api_token = (override or {}).get("api_token") or Config.WHATSAPP_API_TOKEN

        # If not configured, fall back to mock log reporter (no API call made).
        if not api_url:
            logger.info(
                f"💬 [MOCK WHATSAPP CLIENT] To: {recipient_phone}\n"
                f"   Template: {template_name} ({language_code})  Components: {components}\n"
                f"   👉 WHATSAPP_API_URL is missing. Mocking delivery."
            )
            return {"success": True, "called": False, "status": None,
                    "response": "MOCK: WHATSAPP_API_URL not configured; no API call made.",
                    "api_url": None, "message_id": None}

        headers = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        payload = {
            "to": recipient_phone,
            "templateName": template_name,
            "languageCode": language_code or "en_US",
        }
        if components:
            payload["components"] = components

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    body = await resp.text()
                    http_ok = 200 <= resp.status < 300

                    # Prefer the API's own success flag + capture the messageId.
                    success = http_ok
                    message_id = None
                    try:
                        data = json.loads(body) if body else {}
                        if isinstance(data, dict):
                            if "success" in data:
                                success = bool(data["success"]) and http_ok
                            message_id = data.get("messageId") or data.get("message_id")
                    except Exception:
                        pass

                    if success:
                        logger.info(
                            f"✅ WhatsApp template '{template_name}' sent to {recipient_phone} "
                            f"(HTTP {resp.status}, id={message_id})"
                        )
                    else:
                        logger.error(
                            f"❌ WhatsApp API error for '{template_name}' → {recipient_phone}: "
                            f"HTTP {resp.status}: {body}"
                        )
                    return {"success": success, "called": True, "status": resp.status,
                            "response": (body or "")[:2000], "api_url": api_url, "message_id": message_id}
        except Exception as e:
            logger.error(f"❌ Failed to send WhatsApp template to {recipient_phone}: {e}")
            return {"success": False, "called": True, "status": None,
                    "response": f"exception: {e}", "api_url": api_url, "message_id": None}

    @classmethod
    async def send_template_internal(
        cls,
        customer_phone: str,
        tenant_id: str,
        body_parameters: Optional[list] = None,
    ) -> dict:
        """
        Send this tenant's pre-approved WhatsApp template via the unified
        voice-agent endpoint. The service resolves the enterprise's WhatsApp
        account AND which template to send from tenant_id server-side, so we
        send only the recipient, type, tenant, and (optionally) ordered body
        variable values — no template name.

            POST {WHATSAPP_API_URL}/api/internal/voice-agent/send-whatsapp
              headers: x-api-key: <INTERNAL_API_KEY>, Content-Type: application/json
              body:   {"customerPhone","type":"template","tenantId","bodyParameters"?}
              200 ->  {"success": true, "messageId": "wamid..."}

        body_parameters: ordered list of body variable values, e.g. ["John", "ORD-12345"].
        Omit/empty for templates with no body variables.

        Returns a detail dict — never raises.
        """
        customer_phone = (customer_phone or "").strip()
        tenant_id = (tenant_id or "").strip()

        if not customer_phone:
            logger.warning("⚠️ WhatsApp skipped: Empty recipient phone number.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty recipient phone number.", "api_url": None, "message_id": None}
        if not tenant_id:
            logger.warning("⚠️ WhatsApp skipped: Empty tenant id.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty tenant id (agent has no enterprise).", "api_url": None, "message_id": None}

        payload = {"customerPhone": customer_phone, "type": "template", "tenantId": tenant_id}
        if body_parameters:
            payload["bodyParameters"] = list(body_parameters)
        return await cls._post_whatsapp(payload)

    @classmethod
    async def _post_whatsapp(cls, payload: dict) -> dict:
        """POST a payload to the unified WhatsApp endpoint. Never raises.

        WHATSAPP_API_URL is the base host; the endpoint path is appended here.
        """
        base = (Config.WHATSAPP_API_URL or "").rstrip("/")
        api_key = Config.INTERNAL_API_KEY

        # If not configured, fall back to mock log reporter (no API call made).
        if not base:
            logger.info(
                f"💬 [MOCK WHATSAPP CLIENT] {payload}\n"
                f"   👉 WHATSAPP_API_URL is missing. Mocking delivery."
            )
            return {"success": True, "called": False, "status": None,
                    "response": "MOCK: WHATSAPP_API_URL not configured; no API call made.",
                    "api_url": None, "message_id": None}

        path = "/api/internal/voice-agent/send-whatsapp"
        api_url = base if base.endswith(path) else base + path
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key

        _who = f"{payload.get('customerPhone')} (tenant={payload.get('tenantId')}, type={payload.get('type')})"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    body = await resp.text()
                    http_ok = 200 <= resp.status < 300

                    success = http_ok
                    message_id = None
                    try:
                        data = json.loads(body) if body else {}
                        if isinstance(data, dict):
                            if "success" in data:
                                success = bool(data["success"]) and http_ok
                            message_id = data.get("messageId") or data.get("message_id")
                    except Exception:
                        pass

                    if success:
                        logger.info(f"✅ WhatsApp sent to {_who} (HTTP {resp.status}, id={message_id})")
                    else:
                        logger.error(f"❌ WhatsApp API error → {_who}: HTTP {resp.status}: {body}")
                    return {"success": success, "called": True, "status": resp.status,
                            "response": (body or "")[:2000], "api_url": api_url, "message_id": message_id}
        except Exception as e:
            logger.error(f"❌ Failed to send WhatsApp to {_who}: {e}")
            return {"success": False, "called": True, "status": None,
                    "response": f"exception: {e}", "api_url": api_url, "message_id": None}
