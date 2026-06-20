#!/usr/bin/env python3
"""
FastAPI Core Gateway for Voice AI Bot Backend
Integrates modular routes, implements the WebSocket telephony adapter,
and serves a polished interactive dashboard with Swagger / OpenAPI support.
"""

import os
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from config import Config

# Import routes
from routes.call_routes import router as call_router
from routes.bot_routes import router as bot_router

# Configure Logger
logging.basicConfig(level=logging.INFO, format=Config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# Import controllers to track streaming connections
from controllers import bot_controller

# Initialize Core AI Voice Bot Engine based on configuration mode
if Config.VOICE_BOT_MODE == "modular":
    logger.info("🤖 Starting Voice Bot in MODULAR Mode (Deepgram + Gemini + Cartesia)")
    try:
        from core.modular_sales_bot import ModularSalesBot
        sales_bot_engine = ModularSalesBot()
    except Exception as e:
        logger.error(f"❌ Error loading ModularSalesBot, falling back to OpenAI Realtime: {e}")
        from core.openai_realtime_sales_bot import OpenAIRealtimeSalesBot
        sales_bot_engine = OpenAIRealtimeSalesBot()
else:
    logger.info("🤖 Starting Voice Bot in REALTIME Mode (OpenAI Realtime API)")
    from core.openai_realtime_sales_bot import OpenAIRealtimeSalesBot
    sales_bot_engine = OpenAIRealtimeSalesBot()

# Lifespan context manager to handle concurrent background services (e.g., SIP Server)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    sip_task = None
    if Config.USE_SIP_TRUNK:
        logger.info("📡 [Lifespan] USE_SIP_TRUNK is True. Starting Direct SIP Trunking Server in background...")
        try:
            # Run start_server in the background asyncio event loop
            sip_task = asyncio.create_task(sales_bot_engine.start_server())
            logger.info("📡 [Lifespan] SIP Server task scheduled successfully.")
        except Exception as e:
            logger.error(f"❌ [Lifespan] Failed to start/schedule SIP Server: {e}")
            
    yield
    
    # Shutdown logic
    if Config.USE_SIP_TRUNK:
        logger.info("🛑 [Lifespan] Stopping SIP Server...")
        if sales_bot_engine.sip_server:
            try:
                await sales_bot_engine.sip_server.stop()
                logger.info("🛑 [Lifespan] SIP Server stopped successfully.")
            except Exception as e:
                logger.error(f"❌ [Lifespan] Error stopping SIP server: {e}")
        if sip_task and not sip_task.done():
            sip_task.cancel()

# Initialize FastAPI App with customizable description for Swagger Docs
app = FastAPI(
    title="🤖 Enterprise Voice AI Agent API Server",
    description="""
    ## Carrier-Grade Voice AI Backend integration Gateway.
    
    This API suite provides orchestrating endpoints to manage the lifecycle of conversational voice interactions.
    It integrates **OpenAI Realtime API** low-latency speech synthesis with **Exotel SIP/WebSocket** interfaces.
    
    ### Core Operations:
    * **Call Management:** Initiate outbound leads calling campaigns, fetch active telephony status, and register callback webhooks.
    * **AI Personality Configuration:** Hot-reload prompting setups, voice character variants, and models dynamically.
    * **Low-Latency Streaming:** Bridging carrier RTP/PCM16 packets directly with OpenAI endpoints.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "Tech Support Integration Gateway",
        "url": "https://your-enterprise-portal.com",
    },
    lifespan=lifespan
)

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(call_router)
app.include_router(bot_router)

# ==============================================================================
# FastAPI WebSocket Telephony Adapter
# ==============================================================================

class FastAPIWebSocketAdapter:
    """
    Adapter pattern to wrap FastAPI's native WebSocket class, 
    making it fully compatible with websockets.legacy.server.WebSocketServerProtocol
    API methods used by the existing OpenAI Realtime audio streaming engine.
    """
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.remote_address = (websocket.client.host, websocket.client.port) if websocket.client else ("0.0.0.0", 0)
        
    async def send(self, message: str):
        """Send standard JSON strings or audio frames back to telephony stream"""
        await self.websocket.send_text(message)
        
    async def recv(self) -> str:
        """Receive standard JSON strings or audio frames from telephony stream"""
        return await self.websocket.receive_text()
        
    def __aiter__(self):
        return self
        
    async def __anext__(self) -> str:
        try:
            return await self.recv()
        except Exception:
            raise StopAsyncIteration
            
    @property
    def closed(self) -> bool:
        # FastAPI manages connections inside context scope; default to false inside loop
        return False
        
    async def close(self, code: int = 1000):
        """Close connection cleanly"""
        await self.websocket.close(code)

@app.websocket("/stream")
async def websocket_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint - DISABLED in SIP-only mode.
    """
    await websocket.accept()
    logger.warning(f"🔌 [Gateway] Rejected WebSocket stream connection from {websocket.client.host if websocket.client else 'telephony gateway'} (SIP-Only mode active)")
    try:
        await websocket.send_json({"error": "WebSocket streaming is disabled. This server is configured for SIP-Only mode."})
    except Exception:
        pass
    await websocket.close(code=1008) # Policy Violation


# ==============================================================================
# Beautiful Glassmorphic Interactive Home Dashboard
# ==============================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home_dashboard():
    """Renders a beautiful modern portal summarizing gateway status and Swagger interfaces."""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Voice AI Agent Gateway</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #090b11;
                --card-bg: rgba(22, 28, 45, 0.45);
                --accent: #3b82f6;
                --accent-grad: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
                --text: #f3f4f6;
                --text-muted: #9ca3af;
                --border: rgba(255, 255, 255, 0.08);
            }}
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            body {{
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg);
                color: var(--text);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 2rem;
                overflow-x: hidden;
                background-image: 
                    radial-gradient(circle at 10% 20%, rgba(59, 130, 246, 0.08) 0%, transparent 40%),
                    radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.08) 0%, transparent 40%);
            }}
            .container {{
                max-width: 800px;
                width: 100%;
                background: var(--card-bg);
                backdrop-filter: blur(16px);
                -webkit-backdrop-filter: blur(16px);
                border: 1px solid var(--border);
                border-radius: 24px;
                padding: 3rem;
                box-shadow: 0 20px 40px rgba(0,0,0,0.5);
                text-align: center;
                position: relative;
            }}
            .header h1 {{
                font-size: 2.75rem;
                font-weight: 800;
                background: var(--accent-grad);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 0.5rem;
                letter-spacing: -0.03em;
            }}
            .header p {{
                font-size: 1.125rem;
                color: var(--text-muted);
                margin-bottom: 2.5rem;
                font-weight: 300;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 1.5rem;
                margin-bottom: 3rem;
            }}
            .stat-card {{
                background: rgba(255,255,255,0.02);
                border: 1px solid var(--border);
                padding: 1.5rem;
                border-radius: 16px;
                display: flex;
                flex-direction: column;
                align-items: center;
                transition: transform 0.2s ease, border-color 0.2s ease;
            }}
            .stat-card:hover {{
                transform: translateY(-2px);
                border-color: rgba(59, 130, 246, 0.3);
            }}
            .stat-card .label {{
                font-size: 0.875rem;
                text-transform: uppercase;
                color: var(--text-muted);
                letter-spacing: 0.05em;
                margin-bottom: 0.5rem;
            }}
            .stat-card .value {{
                font-size: 1.5rem;
                font-weight: 600;
                color: var(--text);
            }}
            .stat-card .value.active {{
                color: #10b981;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }}
            .pulse-dot {{
                width: 10px;
                height: 10px;
                background-color: #10b981;
                border-radius: 50%;
                box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
                animation: pulse 1.6s infinite;
            }}
            @keyframes pulse {{
                0% {{
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
                }}
                70% {{
                    transform: scale(1);
                    box-shadow: 0 0 0 10px rgba(16, 185, 129, 0);
                }}
                100% {{
                    transform: scale(0.95);
                    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
                }}
            }}
            .btn-container {{
                display: flex;
                gap: 1.25rem;
                justify-content: center;
            }}
            .btn {{
                padding: 1rem 2rem;
                border-radius: 12px;
                font-weight: 600;
                font-size: 1rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.2s ease;
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
            }}
            .btn-primary {{
                background: var(--accent-grad);
                color: white;
                border: none;
                box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
            }}
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(59, 130, 246, 0.45);
            }}
            .btn-secondary {{
                background: transparent;
                color: var(--text);
                border: 1px solid var(--border);
            }}
            .btn-secondary:hover {{
                background: rgba(255, 255, 255, 0.05);
                border-color: var(--text-muted);
                transform: translateY(-2px);
            }}
            .footer {{
                margin-top: 3.5rem;
                font-size: 0.8125rem;
                color: var(--text-muted);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Voice AI Agent Gateway</h1>
                <p>Enterprise Real-Time Speech Telephony API Node</p>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="label">System Status</div>
                    <div class="value active">
                        <span class="pulse-dot"></span> Online
                    </div>
                </div>
                <div class="stat-card">
                    <div class="label">Voice Character</div>
                    <div class="value">{Config.SALES_BOT_NAME} ({Config.OPENAI_VOICE})</div>
                </div>
                <div class="stat-card">
                    <div class="label">Telephony Mode</div>
                    <div class="value">Direct SIP Trunking (SIP Only)</div>
                </div>
                <div class="stat-card">
                    <div class="label">Active SIP Calls</div>
                    <div class="value" style="color: var(--accent);">{len(sales_bot_engine.sip_server.sip_calls) if (sales_bot_engine.sip_server and sales_bot_engine.sip_server.pjsua_initialized) else 0}</div>
                </div>
            </div>
            
            <div class="btn-container">
                <a href="/docs" class="btn btn-primary">
                    ⚡ Open Swagger API Docs
                </a>
                <a href="/redoc" class="btn btn-secondary">
                    📋 Open ReDoc Summary
                </a>
            </div>
            
            <div class="footer">
                &copy; 2026 {Config.COMPANY_NAME}. Protected under secure TLS 1.3 channels.
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check for container orchestration and uptime analytics."""
    sip_calls_count = len(sales_bot_engine.sip_server.sip_calls) if (sales_bot_engine.sip_server and sales_bot_engine.sip_server.pjsua_initialized) else 0
    return {"status": "healthy", "service": "Voice AI Agent Gateway", "concurrency_load": sip_calls_count}
