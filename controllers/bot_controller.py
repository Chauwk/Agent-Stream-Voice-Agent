#!/usr/bin/env python3
"""
Controller: Bot Controller
Handles functional business logic for retrieving sales bot metrics, dynamic runtime configuration, and hot-reload.
"""

import logging
from typing import Dict, Any
from config import Config

logger = logging.getLogger(__name__)

# Track active streaming connections globally (incremented on WebSocket accept, decremented on disconnect)
_active_connections_counter = 0

def increment_active_connections():
    """Increment global active stream counter"""
    global _active_connections_counter
    _active_connections_counter += 1
    logger.debug(f"📈 Active connection incremented: {_active_connections_counter}")

def decrement_active_connections():
    """Decrement global active stream counter"""
    global _active_connections_counter
    if _active_connections_counter > 0:
        _active_connections_counter -= 1
    logger.debug(f"📉 Active connection decremented: {_active_connections_counter}")

async def get_active_bot_telemetry() -> Dict[str, Any]:
    """
    Functional logic to retrieve current sales bot settings, environment state, and active call metrics.
    
    Returns:
        Dict listing active configs and system statistics.
    """
    logger.info("📊 [BotController] Harvesting bot runtime telemetry statistics")
    
    return {
        "success": True,
        "bot_name": Config.SALES_BOT_NAME,
        "company_name": Config.COMPANY_NAME,
        "active_stream_calls": _active_connections_counter,
        "openai_settings": {
            "model": Config.OPENAI_MODEL,
            "voice": Config.OPENAI_VOICE,
            "temperature": Config.OPENAI_TEMPERATURE
        },
        "audio_settings": {
            "sample_rate": Config.SAMPLE_RATE,
            "chunk_size_ms": Config.AUDIO_CHUNK_SIZE,
            "buffer_size_ms": Config.BUFFER_SIZE_MS
        },
        "telephony_mode": {
            "use_sip_trunk": Config.USE_SIP_TRUNK,
            "sip_server_host": Config.SIP_SERVER_HOST,
            "sip_server_port": Config.SIP_SERVER_PORT,
            "sip_public_endpoint": Config.SIP_PUBLIC_IP or "localhost"
        },
        "system_auth": {
            "require_auth": Config.REQUIRE_AUTH,
            "rate_limiting": Config.RATE_LIMITING_ENABLED
        }
    }

async def update_bot_runtime_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Functional logic to dynamically update bot configurations at runtime without restarting the server container.
    
    Args:
        payload: Parameters to update (e.g. sales_bot_name, company_name, openai_voice, openai_temperature).
        
    Returns:
        Dict confirming successful updates and updated configuration state.
    """
    logger.info(f"⚙️ [BotController] Dynamically hot-reloading configurations: {payload}")
    
    updated_fields = []
    
    # Safely apply runtime modifications to Config class variables
    if "sales_bot_name" in payload:
        Config.SALES_BOT_NAME = str(payload["sales_bot_name"])
        Config.SALES_REP_NAME = str(payload["sales_bot_name"])  # Keep alias in sync
        updated_fields.append("sales_bot_name")
        
    if "company_name" in payload:
        Config.COMPANY_NAME = str(payload["company_name"])
        updated_fields.append("company_name")
        
    if "openai_model" in payload:
        Config.OPENAI_MODEL = str(payload["openai_model"])
        updated_fields.append("openai_model")
        
    if "openai_voice" in payload:
        Config.OPENAI_VOICE = str(payload["openai_voice"])
        updated_fields.append("openai_voice")
        
    if "openai_temperature" in payload:
        try:
            Config.OPENAI_TEMPERATURE = float(payload["openai_temperature"])
            updated_fields.append("openai_temperature")
        except ValueError:
            logger.warning(f"⚠️ [BotController] Invalid temperature ignored: {payload['openai_temperature']}")
            
    logger.info(f"✅ [BotController] Dynamic reload complete. Fields modified: {updated_fields}")
    
    return {
        "success": True,
        "updated_fields": updated_fields,
        "current_config": {
            "sales_bot_name": Config.SALES_BOT_NAME,
            "company_name": Config.COMPANY_NAME,
            "openai_model": Config.OPENAI_MODEL,
            "openai_voice": Config.OPENAI_VOICE,
            "openai_temperature": Config.OPENAI_TEMPERATURE
        }
    }
