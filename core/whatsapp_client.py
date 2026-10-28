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
        template_name: str,
        tenant_id: str,
        body_parameters: Optional[list] = None,
    ) -> dict:
        """
        Send a pre-approved WhatsApp template via the internal multi-tenant
        voice-agent endpoint. The service resolves the enterprise's WhatsApp
        account + template (language, components/header) from tenant_id
        server-side, so we send only the template name and ordered body params.

            POST {INTERNAL_WHATSAPP_API_URL}
              headers: x-api-key: <INTERNAL_API_KEY>, Content-Type: application/json
              body:   {"customerPhone","type":"template","templateName","tenantId","bodyParameters"?}
              200 ->  {"success": true, "messageId": "wamid..."}

        body_parameters: ordered list of body variable values, e.g. ["John", "ORD-12345"]
        for a 2-variable template. Omit/empty for templates with no body variables.

        Returns the same detail dict shape as send_template() — never raises.
        """
        customer_phone = (customer_phone or "").strip()
        template_name = (template_name or "").strip()
        tenant_id = (tenant_id or "").strip()

        if not customer_phone:
            logger.warning("⚠️ WhatsApp skipped: Empty recipient phone number.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty recipient phone number.", "api_url": None, "message_id": None}
        if not template_name:
            logger.warning("⚠️ WhatsApp skipped: Empty template name.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty template name.", "api_url": None, "message_id": None}
        if not tenant_id:
            logger.warning("⚠️ WhatsApp skipped: Empty tenant id.")
            return {"success": False, "called": False, "status": None,
                    "response": "Empty tenant id (agent has no enterprise).", "api_url": None, "message_id": None}

        api_url = Config.INTERNAL_WHATSAPP_API_URL
        api_key = Config.INTERNAL_API_KEY

        # If not configured, fall back to mock log reporter (no API call made).
        if not api_url:
            logger.info(
                f"💬 [MOCK WHATSAPP CLIENT] To: {customer_phone}\n"
                f"   Template: {template_name}  tenant: {tenant_id}  bodyParameters: {body_parameters}\n"
                f"   👉 INTERNAL_WHATSAPP_API_URL is missing. Mocking delivery."
            )
            return {"success": True, "called": False, "status": None,
                    "response": "MOCK: INTERNAL_WHATSAPP_API_URL not configured; no API call made.",
                    "api_url": None, "message_id": None}

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key
        payload = {
            "customerPhone": customer_phone,
            "type": "template",
            "templateName": template_name,
            "tenantId": tenant_id,
        }
        if body_parameters:
            payload["bodyParameters"] = list(body_parameters)

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
                        logger.info(
                            f"✅ WhatsApp template '{template_name}' sent to {customer_phone} "
                            f"(tenant={tenant_id}, HTTP {resp.status}, id={message_id})"
                        )
                    else:
                        logger.error(
                            f"❌ Internal WhatsApp API error for '{template_name}' → {customer_phone} "
                            f"(tenant={tenant_id}): HTTP {resp.status}: {body}"
                        )
                    return {"success": success, "called": True, "status": resp.status,
                            "response": (body or "")[:2000], "api_url": api_url, "message_id": message_id}
        except Exception as e:
            logger.error(f"❌ Failed to send internal WhatsApp template to {customer_phone}: {e}")
            return {"success": False, "called": True, "status": None,
                    "response": f"exception: {e}", "api_url": api_url, "message_id": None}
