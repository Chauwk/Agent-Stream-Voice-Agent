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
from routes.company_routes import router as company_router

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

# Lifespan context manager to handle database initialization and background services
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    
    # Initialize Database Tables
    try:
        from models.database import engine, Base
        import models.metadata  # import models to register with Base
        logger.info("🗄️ Initializing metadata database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("🗄️ Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database tables: {e}")

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
app.include_router(company_router)

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

@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_portal():
    """Renders the Enterprise Multi-Tenant RAG Admin Dashboard"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Enterprise Voice AI - Admin Console</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #0b0f19;
                --card-bg: rgba(22, 28, 45, 0.55);
                --accent: #2563eb;
                --accent-hover: #1d4ed8;
                --accent-grad: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
                --text: #f3f4f6;
                --text-muted: #9ca3af;
                --border: rgba(255, 255, 255, 0.08);
                --success: #10b981;
                --error: #ef4444;
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
                background-image: 
                    radial-gradient(circle at 10% 20%, rgba(59, 130, 246, 0.08) 0%, transparent 40%),
                    radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.08) 0%, transparent 40%);
            }}
            header {{
                padding: 1.5rem 2rem;
                background: rgba(15, 23, 42, 0.6);
                backdrop-filter: blur(12px);
                border-bottom: 1px solid var(--border);
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
            }}
            header h1 {{
                font-size: 1.5rem;
                font-weight: 700;
                background: var(--accent-grad);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}
            .header-links a {{
                color: var(--text-muted);
                text-decoration: none;
                margin-left: 1.5rem;
                font-size: 0.9rem;
                transition: color 0.2s;
            }}
            .header-links a:hover {{
                color: var(--text);
            }}
            .main-content {{
                flex: 1;
                max-width: 1200px;
                width: 100%;
                margin: 2rem auto;
                padding: 0 2rem;
                display: grid;
                grid-template-columns: 250px 1fr;
                gap: 2rem;
            }}
            .sidebar {{
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
            }}
            .tab-btn {{
                padding: 0.85rem 1.25rem;
                background: transparent;
                border: 1px solid transparent;
                color: var(--text-muted);
                border-radius: 12px;
                text-align: left;
                font-size: 0.95rem;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }}
            .tab-btn:hover {{
                background: rgba(255,255,255,0.03);
                color: var(--text);
            }}
            .tab-btn.active {{
                background: var(--card-bg);
                border-color: var(--border);
                color: var(--text);
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}
            .sub-tab-btn.active {{
                background: var(--accent) !important;
                color: white !important;
                border-color: var(--accent) !important;
                box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
            }}
            .panel {{
                display: none;
                background: var(--card-bg);
                backdrop-filter: blur(16px);
                border: 1px solid var(--border);
                border-radius: 20px;
                padding: 2.5rem;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }}
            .panel.active {{
                display: block;
            }}
            h2 {{
                font-size: 1.75rem;
                margin-bottom: 1.5rem;
                font-weight: 700;
                letter-spacing: -0.02em;
            }}
            p.panel-desc {{
                color: var(--text-muted);
                font-size: 0.95rem;
                margin-bottom: 2rem;
            }}
            .form-group {{
                margin-bottom: 1.5rem;
            }}
            label {{
                display: block;
                font-size: 0.875rem;
                font-weight: 500;
                color: var(--text-muted);
                margin-bottom: 0.5rem;
            }}
            input[type="text"], select, input[type="file"] {{
                width: 100%;
                padding: 0.75rem 1rem;
                background: rgba(255,255,255,0.03);
                border: 1px solid var(--border);
                border-radius: 10px;
                color: var(--text);
                font-family: inherit;
                font-size: 0.95rem;
                outline: none;
                transition: border-color 0.2s, background 0.2s;
            }}
            input[type="text"]:focus, select:focus {{
                border-color: rgba(59, 130, 246, 0.5);
                background: rgba(255,255,255,0.05);
            }}
            .btn {{
                padding: 0.75rem 1.5rem;
                border-radius: 10px;
                font-weight: 600;
                font-size: 0.95rem;
                cursor: pointer;
                transition: all 0.2s ease;
                display: inline-flex;
                align-items: center;
                gap: 0.5rem;
                border: none;
            }}
            .btn-primary {{
                background: var(--accent-grad);
                color: white;
                box-shadow: 0 4px 15px rgba(59, 130, 246, 0.2);
            }}
            .btn-primary:hover {{
                transform: translateY(-1px);
                box-shadow: 0 6px 20px rgba(59, 130, 246, 0.35);
            }}
            .btn-danger {{
                background: var(--error);
                color: white;
            }}
            .btn-danger:hover {{
                background: #dc2626;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 1rem;
            }}
            th, td {{
                padding: 0.85rem 1rem;
                text-align: left;
                border-bottom: 1px solid var(--border);
                font-size: 0.9rem;
            }}
            th {{
                font-weight: 600;
                color: var(--text-muted);
                text-transform: uppercase;
                font-size: 0.75rem;
                letter-spacing: 0.05em;
            }}
            tr:hover td {{
                background: rgba(255,255,255,0.01);
            }}
            .status-badge {{
                display: inline-block;
                padding: 0.25rem 0.6rem;
                border-radius: 20px;
                font-size: 0.75rem;
                font-weight: 600;
                text-transform: uppercase;
            }}
            .status-processed {{
                background: rgba(16, 185, 129, 0.15);
                color: #10b981;
            }}
            .status-processing {{
                background: rgba(245, 158, 11, 0.15);
                color: #f59e0b;
            }}
            .status-failed {{
                background: rgba(239, 68, 68, 0.15);
                color: #ef4444;
            }}
            .search-results {{
                margin-top: 2rem;
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }}
            .result-card {{
                background: rgba(255,255,255,0.02);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 1.25rem;
            }}
            .result-meta {{
                font-size: 0.75rem;
                color: var(--text-muted);
                margin-bottom: 0.5rem;
                display: flex;
                justify-content: space-between;
            }}
            .result-text {{
                font-size: 0.925rem;
                line-height: 1.5;
            }}
            .alert {{
                padding: 1rem;
                border-radius: 10px;
                margin-bottom: 1.5rem;
                font-size: 0.9rem;
                display: none;
            }}
            .alert-success {{
                background: rgba(16, 185, 129, 0.15);
                color: #10b981;
                border: 1px solid rgba(16, 185, 129, 0.3);
            }}
            .alert-error {{
                background: rgba(239, 68, 68, 0.15);
                color: #ef4444;
                border: 1px solid rgba(239, 68, 68, 0.3);
            }}
            .stat-card-row {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 1.5rem;
                margin-bottom: 2rem;
            }}
            .mini-card {{
                background: rgba(255,255,255,0.02);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 1.25rem;
                text-align: center;
            }}
            .mini-card .label {{
                font-size: 0.75rem;
                color: var(--text-muted);
                text-transform: uppercase;
                margin-bottom: 0.25rem;
            }}
            .mini-card .value {{
                font-size: 1.5rem;
                font-weight: 600;
            }}
            footer {{
                text-align: center;
                padding: 2rem;
                font-size: 0.8rem;
                color: var(--text-muted);
                border-top: 1px solid var(--border);
                background: rgba(15, 23, 42, 0.2);
            }}
        </style>
    </head>
    <body>
        <header>
            <h1>Voice AI Bot - Admin Console</h1>
            <div class="header-links">
                <a href="/">Home Dashboard</a>
                <a href="/docs" target="_blank">Swagger API</a>
            </div>
        </header>

        <div class="main-content">
            <!-- Sidebar Navigation -->
            <div class="sidebar">
                <button class="tab-btn active" onclick="switchTab('status-panel', this)">
                    📊 Telephony Status
                </button>
                <button class="tab-btn" onclick="switchTab('companies-panel', this)">
                    🏢 Company Tenants
                </button>
                <button class="tab-btn" onclick="switchTab('docs-panel', this)">
                    📂 RAG Document Store
                </button>
                <button class="tab-btn" onclick="switchTab('sandbox-panel', this)">
                    🔍 Vector Search Sandbox
                </button>
            </div>

            <!-- Content Panels -->
            <div class="panels-container">
                <!-- Tab 1: Status -->
                <div id="status-panel" class="panel active">
                    <h2>Telephony & Bot Status</h2>
                    <p class="panel-desc">Real-time status of current bot configurations and SIP calls.</p>
                    
                    <div class="stat-card-row">
                        <div class="mini-card">
                            <div class="label">System State</div>
                            <div class="value" style="color: #10b981;">Online</div>
                        </div>
                        <div class="mini-card">
                            <div class="label">Active Calls</div>
                            <div class="value" id="active-calls-val" style="color: var(--accent);">0</div>
                        </div>
                        <div class="mini-card">
                            <div class="label">Running Mode</div>
                            <div class="value" id="running-mode-val" style="text-transform: capitalize;">-</div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 2rem;">
                        <h3>Active Engine Settings</h3>
                        <table style="margin-top: 1rem;">
                            <tbody>
                                <tr>
                                    <td>Voice Bot Name</td>
                                    <td id="cfg-bot-name">-</td>
                                </tr>
                                <tr>
                                    <td>Company Registry</td>
                                    <td id="cfg-company-name">-</td>
                                </tr>
                                <tr>
                                    <td>STT Model (Deepgram)</td>
                                    <td id="cfg-stt-model">-</td>
                                </tr>
                                <tr>
                                    <td>LLM Model (Gemini)</td>
                                    <td id="cfg-llm-model">-</td>
                                </tr>
                                <tr>
                                    <td>TTS Model (Sarvam)</td>
                                    <td id="cfg-tts-model">-</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Tab 2: Companies -->
                <div id="companies-panel" class="panel">
                    <h2>Company Registry Settings</h2>
                    <p class="panel-desc">Manage multi-tenant company configurations. Each company maps to a unique Exotel virtual phone number.</p>
                    
                    <div id="company-alert" class="alert"></div>

                    <!-- Register Company Form -->
                    <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border); padding: 1.5rem; border-radius: 12px; margin-bottom: 2rem;">
                        <h3>Register New Company DID</h3>
                        <form id="create-company-form" onsubmit="handleCreateCompany(event)" style="margin-top: 1rem; display: grid; grid-template-columns: 1fr 1fr auto; gap: 1rem; align-items: end;">
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="comp-name">Company Name</label>
                                <input type="text" id="comp-name" required placeholder="e.g. Acme Corp">
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="comp-phone">Virtual DID Phone Number</label>
                                <input type="text" id="comp-phone" required placeholder="e.g. 91804709XXXX">
                            </div>
                            <button type="submit" class="btn btn-primary">Add Company</button>
                        </form>
                    </div>

                    <h3>Registered Businesses</h3>
                    <table id="companies-table" style="margin-top: 1rem;">
                        <thead>
                            <tr>
                                <th>Company Name</th>
                                <th>Virtual Phone Number</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="companies-list">
                            <tr>
                                <td colspan="3" style="text-align: center; color: var(--text-muted);">Loading companies...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Tab 3: RAG Upload -->
                <div id="docs-panel" class="panel">
                    <h2>RAG Document Indexer</h2>
                    <p class="panel-desc">Ingest knowledge bases from multiple sources. We support file uploads (PDF, TXT, DOCX, PPTX), website crawling, and custom text messages/FAQ data.</p>
                    
                    <div id="docs-alert" class="alert"></div>

                    <!-- Source Sub-Tabs -->
                    <div style="display: flex; gap: 0.75rem; margin-bottom: 1.75rem;">
                        <button class="btn btn-secondary sub-tab-btn active" id="sub-tab-files" onclick="switchSubTab('files')">📂 Files Ingest</button>
                        <button class="btn btn-secondary sub-tab-btn" id="sub-tab-web" onclick="switchSubTab('web')">🌐 Web Link Ingest</button>
                        <button class="btn btn-secondary sub-tab-btn" id="sub-tab-text" onclick="switchSubTab('text')">📝 Text Message Ingest</button>
                    </div>

                    <!-- Ingest Section 1: Files -->
                    <div id="ingest-files-section" class="ingest-section" style="background: rgba(255,255,255,0.01); border: 1px solid var(--border); padding: 1.5rem; border-radius: 12px; margin-bottom: 2rem;">
                        <h3>Index Files for Tenant</h3>
                        <form id="upload-docs-form" onsubmit="handleUploadDocs(event)" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 1.25rem;">
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="upload-company-select">Select Company Context</label>
                                <select id="upload-company-select" class="company-select-shared" required>
                                    <option value="">-- Select Company --</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="upload-files">Upload Reference Documents (PDF, TXT, DOCX, PPTX)</label>
                                <input type="file" id="upload-files" multiple required accept=".txt,.pdf,.docx,.pptx,.ppt">
                            </div>
                            <div>
                                <button type="submit" id="upload-submit-btn" class="btn btn-primary">🚀 Upload & Index Document</button>
                            </div>
                        </form>
                    </div>

                    <!-- Ingest Section 2: Web Links -->
                    <div id="ingest-web-section" class="ingest-section" style="display: none; background: rgba(255,255,255,0.01); border: 1px solid var(--border); padding: 1.5rem; border-radius: 12px; margin-bottom: 2rem;">
                        <h3>Index Website Link for Tenant</h3>
                        <form id="upload-web-form" onsubmit="handleUploadWeb(event)" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 1.25rem;">
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="web-company-select">Select Company Context</label>
                                <select id="web-company-select" class="company-select-shared" required>
                                    <option value="">-- Select Company --</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="web-url">Website URL to Crawl & Extract Text</label>
                                <input type="text" id="web-url" required placeholder="e.g. https://yourcompany.com/pricing">
                            </div>
                            <div>
                                <button type="submit" id="web-submit-btn" class="btn btn-primary">🌐 Crawl & Index Webpage</button>
                            </div>
                        </form>
                    </div>

                    <!-- Ingest Section 3: Raw Text Messages -->
                    <div id="ingest-text-section" class="ingest-section" style="display: none; background: rgba(255,255,255,0.01); border: 1px solid var(--border); padding: 1.5rem; border-radius: 12px; margin-bottom: 2rem;">
                        <h3>Index Custom Text / Text Messages for Tenant</h3>
                        <form id="upload-text-form" onsubmit="handleUploadText(event)" style="margin-top: 1rem; display: flex; flex-direction: column; gap: 1.25rem;">
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="text-company-select">Select Company Context</label>
                                <select id="text-company-select" class="company-select-shared" required>
                                    <option value="">-- Select Company --</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="text-source-name">Source Label (e.g. support_notes)</label>
                                <input type="text" id="text-source-name" required placeholder="e.g. sms_logs_or_faq_updates">
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="text-content">Raw Text Message Data / FAQ Details</label>
                                <textarea id="text-content" required placeholder="Paste text messages, logs, or custom notes here..." style="width: 100%; height: 150px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 10px; color: var(--text); padding: 0.75rem 1rem; font-family: inherit; font-size: 0.95rem; resize: vertical; outline: none;"></textarea>
                            </div>
                            <div>
                                <button type="submit" id="text-submit-btn" class="btn btn-primary">📝 Index Custom Text</button>
                            </div>
                        </form>
                    </div>

                    <div id="company-documents-section" style="display: none;">
                        <h3 id="company-docs-title">Documents List</h3>
                        <table style="margin-top: 1rem;">
                            <thead>
                                <tr>
                                    <th>Filename</th>
                                    <th>Size</th>
                                    <th>Uptime</th>
                                    <th>RAG Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="company-docs-list"></tbody>
                        </table>
                    </div>
                </div>

                <!-- Tab 4: Vector Search sandbox -->
                <div id="sandbox-panel" class="panel">
                    <h2>Knowledge Base Search sandbox</h2>
                    <p class="panel-desc">Simulate and test vector database retrieval. Select a company and submit query prompts to inspect similarity hits.</p>
                    
                    <div style="background: rgba(255,255,255,0.01); border: 1px solid var(--border); padding: 1.5rem; border-radius: 12px;">
                        <h3>Query Test</h3>
                        <form id="sandbox-search-form" onsubmit="handleSandboxSearch(event)" style="margin-top: 1rem; display: grid; grid-template-columns: 1fr 2fr auto; gap: 1rem; align-items: end;">
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="search-company-select">Company context</label>
                                <select id="search-company-select" required>
                                    <option value="">-- Select Company --</option>
                                </select>
                            </div>
                            <div class="form-group" style="margin-bottom: 0;">
                                <label for="search-query">Search Query</label>
                                <input type="text" id="search-query" required placeholder="Ask details about company services, pricing, or support rules...">
                            </div>
                            <button type="submit" class="btn btn-primary">Search DB</button>
                        </form>
                    </div>

                    <div class="search-results" id="search-sandbox-results"></div>
                </div>
            </div>
        </div>

        <footer>
            &copy; 2026 {Config.COMPANY_NAME}. All administrative actions are logged and encrypted.
        </footer>

        <script>
            // Tab Switch Logic
            function switchTab(panelId, btn) {{
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                
                document.getElementById(panelId).classList.add('active');
                btn.classList.add('active');
                
                if (panelId === 'companies-panel' || panelId === 'docs-panel' || panelId === 'sandbox-panel') {{
                    loadCompanies();
                }}
            }}

            // Show alert box
            function showAlert(alertId, message, isError = false) {{
                const alertEl = document.getElementById(alertId);
                alertEl.innerText = message;
                alertEl.className = 'alert ' + (isError ? 'alert-error' : 'alert-success');
                alertEl.style.display = 'block';
                setTimeout(() => {{
                    alertEl.style.display = 'none';
                }}, 6000);
            }}

            // Load companies from DB
            let cachedCompanies = [];
            async function loadCompanies() {{
                try {{
                    const response = await fetch('/companies/');
                    if (!response.ok) throw new Error('Failed to load companies');
                    const data = await response.json();
                    cachedCompanies = data;
                    
                    // Render List
                    const listEl = document.getElementById('companies-list');
                    if (data.length === 0) {{
                        listEl.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No companies registered yet. Add a new company above!</td></tr>`;
                    }} else {{
                        listEl.innerHTML = data.map(c => `
                            <tr>
                                <td><strong>${{c.name}}</strong></td>
                                <td><code>${{c.phone_number}}</code></td>
                                <td>
                                    <button class="btn btn-danger" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;" onclick="handleDeleteCompany('${{c.company_id}}')">Delete</button>
                                </td>
                            </tr>
                        `).join('');
                    }}
                    
                    // Populate Select Dropdowns
                    const selectElList = document.querySelectorAll('.company-select-shared, #search-company-select');
                    selectElList.forEach(selectEl => {{
                        const currentVal = selectEl.value;
                        selectEl.innerHTML = '<option value="">-- Select Company --</option>' + 
                            data.map(c => `<option value="${{c.company_id}}">${{c.name}} (${{c.phone_number}})</option>`).join('');
                        selectEl.value = currentVal;
                    }});
                }} catch (err) {{
                    console.error(err);
                }}
            }}

            // Fetch telemetry data
            async function loadTelemetry() {{
                try {{
                    const res = await fetch('/api/v1/bot/status');
                    if (!res.ok) return;
                    const data = await res.json();
                    
                    document.getElementById('active-calls-val').innerText = data.active_stream_calls;
                    document.getElementById('running-mode-val').innerText = data.modular_settings.voice_bot_mode;
                    
                    document.getElementById('cfg-bot-name').innerText = data.bot_name;
                    document.getElementById('cfg-company-name').innerText = data.company_name;
                    document.getElementById('cfg-stt-model').innerText = data.modular_settings.deepgram_model;
                    document.getElementById('cfg-llm-model').innerText = data.modular_settings.gemini_model;
                    document.getElementById('cfg-tts-model').innerText = data.modular_settings.sarvam_model;
                }} catch (err) {{
                    console.error(err);
                }}
            }}

            // Create new Company
            async function handleCreateCompany(e) {{
                e.preventDefault();
                const name = document.getElementById('comp-name').value;
                const phone = document.getElementById('comp-phone').value;
                
                try {{
                    const response = await fetch(`/companies/?name=${{encodeURIComponent(name)}}&phone_number=${{encodeURIComponent(phone)}}`, {{
                        method: 'POST'
                    }});
                    const result = await response.json();
                    if (!response.ok) {{
                        throw new Error(result.detail || 'Failed to create company');
                    }}
                    showAlert('company-alert', `Successfully registered company: ${{name}}`);
                    document.getElementById('create-company-form').reset();
                    loadCompanies();
                }} catch (err) {{
                    showAlert('company-alert', err.message, true);
                }}
            }}

            // Delete Company
            async function handleDeleteCompany(companyId) {{
                if (!confirm("Are you sure you want to delete this company and all of its document vectors? This cannot be undone.")) return;
                
                try {{
                    const response = await fetch(`/companies/${{companyId}}`, {{
                        method: 'DELETE'
                    }});
                    const result = await response.json();
                    if (!response.ok) {{
                        throw new Error(result.detail || 'Failed to delete company');
                    }}
                    showAlert('company-alert', 'Company successfully deleted.');
                    loadCompanies();
                }} catch (err) {{
                    showAlert('company-alert', err.message, true);
                }}
            }}

            // Upload Document to S3 / Chroma DB
            async function handleUploadDocs(e) {{
                e.preventDefault();
                const companyId = document.getElementById('upload-company-select').value;
                const fileInput = document.getElementById('upload-files');
                const submitBtn = document.getElementById('upload-submit-btn');
                let progressBar = document.getElementById('upload-progress-container');

                if (!companyId) return alert("Please select a company first.");
                if (fileInput.files.length === 0) return alert("Select at least one document.");

                const formData = new FormData();
                for (let i = 0; i < fileInput.files.length; i++) {{
                    formData.append("files", fileInput.files[i]);
                }}

                submitBtn.disabled = true;
                submitBtn.innerText = "⏫ Uploading...";

                // Show progress container
                if (!progressBar) {{
                    progressBar = document.createElement('div');
                    progressBar.id = 'upload-progress-container';
                    progressBar.style.cssText = 'margin-top:12px;padding:12px;background:rgba(255,255,255,0.05);border-radius:8px;border:1px solid rgba(255,255,255,0.1);';
                    progressBar.innerHTML =
                        '<div id="upload-progress-label" style="font-size:13px;color:#a0aec0;margin-bottom:6px;">Starting upload...</div>' +
                        '<div style="background:rgba(255,255,255,0.1);border-radius:99px;height:8px;overflow:hidden;">' +
                            '<div id="upload-progress-fill" style="height:100%;width:0%;background:linear-gradient(90deg,#667eea,#764ba2);border-radius:99px;transition:width 0.4s ease;"></div>' +
                        '</div>' +
                        '<div id="upload-progress-pct" style="font-size:12px;color:#667eea;margin-top:4px;text-align:right;">0%</div>';
                    submitBtn.parentNode.insertBefore(progressBar, submitBtn.nextSibling);
                }}
                progressBar.style.display = 'block';
                document.getElementById('upload-progress-label').innerText = 'Uploading file...';
                document.getElementById('upload-progress-fill').style.width = '0%';
                document.getElementById('upload-progress-pct').innerText = '0%';

                try {{
                    // Step 1: Submit — returns immediately with job_id(s)
                    const response = await fetch(`/companies/${{companyId}}/documents`, {{
                        method: 'POST',
                        body: formData
                    }});
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || 'Upload failed');

                    // Step 2: Poll each job for progress
                    const jobs = result.jobs || [];
                    for (const job of jobs) {{
                        submitBtn.innerText = '⚙️ Indexing ' + job.filename + '...';
                        document.getElementById('upload-progress-label').innerText = 'Indexing: ' + job.filename;
                        await pollJobProgress(job.job_id);
                    }}

                    showAlert('docs-alert', `✅ Document(s) uploaded and indexed successfully!`);
                    fileInput.value = '';
                    fetchCompanyDocs(companyId);
                }} catch (err) {{
                    showAlert('docs-alert', err.message, true);
                }} finally {{
                    submitBtn.disabled = false;
                    submitBtn.innerText = "🚀 Upload & Index Document";
                    setTimeout(() => {{ if(progressBar) progressBar.style.display = 'none'; }}, 3000);
                }}
            }}

            // Poll a job until done, updating the progress bar
            async function pollJobProgress(jobId) {{
                return new Promise((resolve, reject) => {{
                    const interval = setInterval(async () => {{
                        try {{
                            const res = await fetch(`/companies/jobs/${{jobId}}`);
                            if (!res.ok) {{ clearInterval(interval); return reject(new Error('Job not found')); }}
                            const job = await res.json();

                            const pct = job.total > 0 ? Math.round((job.progress / job.total) * 100) : 5;
                            document.getElementById('upload-progress-fill').style.width = pct + '%';
                            document.getElementById('upload-progress-pct').innerText = pct + '%';
                            document.getElementById('upload-progress-label').innerText = job.message || 'Processing...';

                            if (job.status === 'done') {{
                                document.getElementById('upload-progress-fill').style.width = '100%';
                                document.getElementById('upload-progress-pct').innerText = '100%';
                                clearInterval(interval);
                                resolve();
                            }} else if (job.status === 'error') {{
                                clearInterval(interval);
                                reject(new Error(job.message || 'Indexing failed'));
                            }}
                        }} catch(e) {{ clearInterval(interval); reject(e); }}
                    }}, 1000);
                }});
            }}

            // Crawl & Index Webpage URL
            async function handleUploadWeb(e) {{
                e.preventDefault();
                const companyId = document.getElementById('web-company-select').value;
                const url = document.getElementById('web-url').value;
                const submitBtn = document.getElementById('web-submit-btn');
                
                if (!companyId) return alert("Please select a company first.");
                
                submitBtn.disabled = true;
                submitBtn.innerText = "Crawling & indexing URL... Please wait...";
                
                try {{
                    const response = await fetch(`/companies/${{companyId}}/webpages?url=${{encodeURIComponent(url)}}`, {{
                        method: 'POST'
                    }});
                    const result = await response.json();
                    if (!response.ok) {{
                        throw new Error(result.detail || 'Crawling failed');
                    }}
                    showAlert('docs-alert', `Webpage successfully crawled and indexed.`);
                    document.getElementById('web-url').value = '';
                    fetchCompanyDocs(companyId);
                }} catch (err) {{
                    showAlert('docs-alert', err.message, true);
                }} finally {{
                    submitBtn.disabled = false;
                    submitBtn.innerText = "🌐 Crawl & Index Webpage";
                }}
            }}

            // Index Raw Text Messages
            async function handleUploadText(e) {{
                e.preventDefault();
                const companyId = document.getElementById('text-company-select').value;
                const sourceName = document.getElementById('text-source-name').value;
                const textVal = document.getElementById('text-content').value;
                const submitBtn = document.getElementById('text-submit-btn');
                
                if (!companyId) return alert("Please select a company first.");
                
                submitBtn.disabled = true;
                submitBtn.innerText = "Indexing custom text... Please wait...";
                
                try {{
                    const response = await fetch(`/companies/${{companyId}}/text`, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ text: textVal, source_name: sourceName }})
                    }});
                    const result = await response.json();
                    if (!response.ok) {{
                        throw new Error(result.detail || 'Indexing failed');
                    }}
                    showAlert('docs-alert', `Custom text successfully indexed.`);
                    document.getElementById('text-source-name').value = '';
                    document.getElementById('text-content').value = '';
                    fetchCompanyDocs(companyId);
                }} catch (err) {{
                    showAlert('docs-alert', err.message, true);
                }} finally {{
                    submitBtn.disabled = false;
                    submitBtn.innerText = "📝 Index Custom Text";
                }}
            }}

            // Fetch company documents
            async function fetchCompanyDocs(companyId) {{
                if (!companyId) return;
                try {{
                    const response = await fetch(`/companies/${{companyId}}`);
                    if (!response.ok) return;
                    const data = await response.json();
                    
                    const docSection = document.getElementById('company-documents-section');
                    const listEl = document.getElementById('company-docs-list');
                    
                    if (data.documents && data.documents.length > 0) {{
                        docSection.style.display = 'block';
                        listEl.innerHTML = data.documents.map(d => `
                            <tr>
                                <td>${{d.filename}}</td>
                                <td>${{(d.size_bytes / 1024).toFixed(1)}} KB</td>
                                <td>${{new Date(d.uploaded_at).toLocaleString()}}</td>
                                <td><span class="status-badge status-${{d.status}}">${{d.status}}</span></td>
                                <td>
                                    <button class="btn btn-danger" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;" onclick="handleDeleteDoc('${{companyId}}', ${{d.id}})">Delete</button>
                                </td>
                            </tr>
                        `).join('');
                    }} else {{
                        docSection.style.display = 'none';
                    }}
                }} catch (err) {{
                    console.error(err);
                }}
            }}

            // Delete individual document
            async function handleDeleteDoc(companyId, docId) {{
                if (!confirm("Are you sure you want to delete this document and all of its associated vector chunks?")) return;
                
                try {{
                    const response = await fetch(`/companies/${{companyId}}/documents/${{docId}}`, {{
                        method: 'DELETE'
                    }});
                    const result = await response.json();
                    if (!response.ok) {{
                        throw new Error(result.detail || 'Failed to delete document');
                    }}
                    showAlert('docs-alert', 'Document and vectors successfully deleted.');
                    fetchCompanyDocs(companyId);
                }} catch (err) {{
                    showAlert('docs-alert', err.message, true);
                }}
            }}

            // Sub-tab navigation logic
            function switchSubTab(subTabType) {{
                document.querySelectorAll('.sub-tab-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.ingest-section').forEach(sec => sec.style.display = 'none');
                
                if (subTabType === 'files') {{
                    document.getElementById('sub-tab-files').classList.add('active');
                    document.getElementById('ingest-files-section').style.display = 'block';
                }} else if (subTabType === 'web') {{
                    document.getElementById('sub-tab-web').classList.add('active');
                    document.getElementById('ingest-web-section').style.display = 'block';
                }} else if (subTabType === 'text') {{
                    document.getElementById('sub-tab-text').classList.add('active');
                    document.getElementById('ingest-text-section').style.display = 'block';
                }}
            }}

            // Sync all company select dropdown values and fetch documents
            document.querySelectorAll('.company-select-shared').forEach(select => {{
                select.addEventListener('change', (e) => {{
                    const companyId = e.target.value;
                    document.querySelectorAll('.company-select-shared').forEach(s => s.value = companyId);
                    if (companyId) {{
                        fetchCompanyDocs(companyId);
                    }} else {{
                        document.getElementById('company-documents-section').style.display = 'none';
                    }}
                }});
            }});

            // RAG Search Sandbox Testing
            async function handleSandboxSearch(e) {{
                e.preventDefault();
                const companyId = document.getElementById('search-company-select').value;
                const query = document.getElementById('search-query').value;
                const resultsEl = document.getElementById('search-sandbox-results');
                
                if (!companyId) return alert("Select a company first.");
                
                resultsEl.innerHTML = '<div style="text-align: center; color: var(--text-muted);">Querying vector database...</div>';
                
                try {{
                    const response = await fetch(`/companies/${{companyId}}/search?q=${{encodeURIComponent(query)}}&top_k=3`);
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || 'Search failed');
                    
                    if (data.length === 0) {{
                        resultsEl.innerHTML = '<div style="text-align: center; color: var(--text-muted); border: 1px dashed var(--border); padding: 2rem; border-radius: 12px;">No matching documents found in the database for this query. Make sure files are indexed!</div>';
                        return;
                    }}
                    
                    resultsEl.innerHTML = data.map((r, idx) => `
                        <div class="result-card">
                            <div class="result-meta">
                                <span>Hit #${{idx + 1}} | Source: <strong>${{r.source || 'Unknown'}}</strong></span>
                                <span>Similarity Match</span>
                            </div>
                            <div class="result-text">"${{r.chunk}}"</div>
                        </div>
                    `).join('');
                }} catch (err) {{
                    resultsEl.innerHTML = `<div style="color: var(--error); border: 1px solid rgba(239,68,68,0.2); padding: 1.5rem; border-radius: 12px; background: rgba(239,68,68,0.05);">Search failed: ${{err.message}}</div>`;
                }}
            }}

            // Run loops
            loadTelemetry();
            setInterval(loadTelemetry, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check for container orchestration and uptime analytics."""
    sip_calls_count = len(sales_bot_engine.sip_server.sip_calls) if (sales_bot_engine.sip_server and sales_bot_engine.sip_server.pjsua_initialized) else 0
    return {"status": "healthy", "service": "Voice AI Agent Gateway", "concurrency_load": sip_calls_count}

