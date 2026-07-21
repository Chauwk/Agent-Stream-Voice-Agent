# 🤖 Agent-Stream Voice AI Platform

An enterprise-grade, multi-tenant conversational Voice AI platform engineered for ultra-low latency telephone and web-based interactions. The system bridges **Exotel Telephony (vSIP Trunking & REST API)** and **Web Browsers** with dual AI pipeline engines: a **Modular STT-LLM-TTS Pipeline** (Deepgram + Gemini + Sarvam AI) and **OpenAI Realtime Speech-to-Speech**.

---

## 🏗️ Architecture & Core Components

```mermaid
flowchart TD
    subgraph Clients["Incoming Channels"]
        EX_IN["Exotel Inbound Trunk (vSIP Port 5060)"]
        EX_OUT["Exotel Outbound REST API (/connect.json)"]
        WEB_WIDGET["Web Browser (<agent-stream-voice> Widget)"]
    end

    subgraph Gateway["FastAPI API Gateway & PJSIP Telephony Engine"]
        SIP["PJSIP Native SIP Server (Port 5060)"]
        API["FastAPI App Server (Port 5000)"]
        SECURITY["IP Whitelist & Spoofing Guard (is_valid_exotel)"]
    end

    subgraph DualEngines["Dual Processing Modes (VOICE_BOT_MODE)"]
        subgraph ModularEngine["Mode 1: Modular Pipeline"]
            DG["Deepgram STT (nova-2-phonecall)"]
            GEMINI["Gemini 2.5 Flash (LLM)"]
            SARVAM["Sarvam AI TTS (bulbul:v3)"]
        end
        subgraph RealtimeEngine["Mode 2: OpenAI Realtime"]
            OAI["OpenAI Realtime API (Speech-to-Speech)"]
        end
    end

    subgraph DataStorage["Data & Knowledge Layer"]
        MONGO[("MongoDB Atlas (Agents, Logs, KB)")]
        CHROMA[("ChromaDB Vector Store")]
        S3[("AWS S3 Bucket (Documents Storage)")]
        ZOHO["Zoho SMTP (Email Automations)"]
    end

    EX_IN --> SECURITY --> SIP
    EX_OUT --> API
    WEB_WIDGET --> API

    SIP <-->|Linear16 PCM Audio| ModularEngine
    SIP <-->|G.711 / PCM Audio| RealtimeEngine
    API <-->|WebSocket Streaming| ModularEngine

    GEMINI -->|Tool Call: query_knowledge_base| CHROMA
    GEMINI -->|Tool Call: send_email| ZOHO
    ModularEngine -->|Call Logs & Analytics| MONGO
    RealtimeEngine -->|Call Logs| MONGO
    CHROMA <-->|Document Sync| S3
```

---

## 📞 Telephony & Connectivity Models

### 1. Inbound SIP Trunking (Exotel vSIP)
* **Direct PJSIP Connection**: Listens on port `5060` (TCP/UDP) over public IP. Does **not** require Exotel URL/Flow Applets.
* **IP-Based Authentication & Security**:
  * Authenticates originating carrier IPs against trusted Exotel ranges (`103.111.29.x`, `202.162.247.x`, etc.).
  * **Header Spoofing Defense**: Blocks unauthorized private network range fallbacks (`10.x`, `192.168.x`, `172.x`) in production mode to eliminate unauthorized scanner calls.

### 2. Outbound Telephony (Exotel REST API)
* **API Endpoint**: Uses Exotel's direct peer-to-peer connect API (`/v1/Accounts/{AccountSid}/Calls/connect.json`).
* **Two-Leg Dialing**: Dials the customer (`From`) first. Upon pickup, bridges to the Exotel Virtual DID (`To` / `CallerId`), which routes to our PJSIP trunk.
* **Automated Number Formatting**: Automatically formats Indian 10-digit mobile numbers with a leading `0` (e.g., `09553856533`) to ensure carrier validation.

### 3. Embeddable Web Component & Browser Streaming
* **`<agent-stream-voice>` Web Component**: Easily embeddable JavaScript widget (`/static/widget.js`) for direct in-browser voice interactions.
* **WebSocket Endpoint**: `ws://<host>:5000/api/v1/ws/browser-stream?agent_id=<id>` streaming 16kHz PCM audio.

---

## ⚡ Dual AI Processing Engines

The active engine is selected using the `VOICE_BOT_MODE` environment variable.

### Mode 1: Modular Pipeline (`VOICE_BOT_MODE=modular`)
Designed for cost-efficiency, localized Indian voice synthesis, and high control.
* **Speech-to-Text (STT)**: **Deepgram WebSocket** (`nova-2-phonecall` model, multilingual, streaming 16kHz linear16 PCM).
* **LLM Engine**: **Gemini 2.5 Flash** (`gemini-2.5-flash` via Google GenAI SDK with Vertex AI or AI Studio). Features dynamic tool calling (`query_knowledge_base`, `send_email`, `end_call`).
* **Text-to-Speech (TTS)**: **Sarvam AI WebSocket & HTTP Fallback** (`bulbul:v3` model). Supports multiple Indian speakers (`neha`, `shubh`, `ishita`), pace adjustment, and digital audio gain.

### Mode 2: OpenAI Realtime Speech-to-Speech (`VOICE_BOT_MODE=realtime`)
Designed for ultra-low latency end-to-end conversational naturalness.
* **Speech-to-Speech**: Direct WebSocket connection to `gpt-4o-realtime-preview-2024-12-17` or `gpt-realtime`.
* **Native Audio Processing**: Direct G.711 / PCM audio streaming with native interruption handling and function calling support.

---

## 🚀 Key Subsystems & Features

### 🏢 Multi-Tenant RAG (Retrieval-Augmented Generation)
* **Document Parsing**: Uploads PDF, DOCX, and TXT files per agent/company.
* **Vector Store**: Embeddings generated via Vertex AI / OpenAI and indexed in **ChromaDB** with strict tenant isolation (`knowledgeBaseIds`).
* **Persistent Backup**: Raw files backed up to AWS S3 (`chauwk-aivoiceagent-stream`).

### 📧 Automated SMTP Email & Post-Call System
* **Async SMTP Client**: `core/email_client.py` wrapping `smtplib` in non-blocking `asyncio.to_thread` (configured for **Zoho SMTP** `smtp.zoho.in:465`).
* **Live In-Call Tool**: Bot triggers real-time emails during active calls via `send_email` tool.
* **Post-Call Lead Trigger**: Automatically extracts customer details and sends structured lead summaries to `abhishek.gupta@gmail.com` (CC: `partnerships.3@chauwk.com`).
* **Smart Noise Filter**: Prevents phantom/empty call email alerts by ignoring initial prompt seeding and system silence messages (`System:...`).

### 📊 Gemini-Powered Call Analytics
* On call completion, `core/analytics_manager.py` analyzes the full transcript using Gemini to extract:
  * Customer Name, Address, Email, Provided Phone Number
  * Meeting Consent (`Yes`/`No`) & Field Visit Request (`Yes`/`No`)
  * Business Interest & Executive Call Summary
* All structured data is saved to **MongoDB Atlas**.

### 🛡️ Operational Safeguards
* **Hot-Reload Voice Tuning**: Dynamically adjust Sarvam speaker, speaking speed (pace), and digital audio gain via API/Dashboard without container restarts.
* **Emergency Engine Switch (`DISABLE_AI_ENGINES`)**: Setting `DISABLE_AI_ENGINES=true` in `.env` forces PJSIP to instantly reject incoming calls with `503 Service Unavailable`, preventing credit consumption while keeping the web portal online.

---

## 🛠️ Project Structure

```
├── api_gateway.py           # Main FastAPI Application & Management Portal
├── config.py                # Centralized configuration & environment loader
├── Dockerfile               # Production Docker container definition (Python 3.10 + PJSIP + Playwright)
├── docker-compose.yml       # Stack orchestration (Voice Bot + ChromaDB)
├── controllers/             # Business logic controllers
│   ├── bot_controller.py
│   ├── call_controller.py
│   └── company_controller.py
├── core/                    # Core engines & integrations
│   ├── agent_resolver.py     # Multi-tenant agent lookup & knowledge filtering
│   ├── analytics_manager.py  # Gemini post-call transcript analytics
│   ├── bot_framework.py      # Dynamic bot configurations & templates
│   ├── email_client.py       # Asynchronous SMTP client (Zoho SMTP)
│   ├── exotel_outbound_api.py# Exotel REST Connect API outbound caller
│   ├── modular_sales_bot.py  # Deepgram + Gemini + Sarvam pipeline engine
│   ├── mongo_manager.py      # MongoDB Atlas connection manager
│   ├── openai_realtime_sales_bot.py # OpenAI Realtime Speech-to-Speech engine
│   ├── rag_manager.py        # ChromaDB vector search & document indexing
│   └── sip_server.py         # Native PJSIP C-library wrapper & SIP server
├── routes/                  # API Route Definitions
│   ├── agent_routes.py       # Agent CRUD, KB document uploads, & web settings
│   ├── bot_routes.py         # Bot dynamic configuration & voice tuning
│   ├── call_routes.py        # Outbound call initiation & webhooks
│   └── company_routes.py     # Enterprise company management & KB APIs
├── static/                  # Static assets & Web Component widget
│   └── widget.js            # <agent-stream-voice> Web Component script
└── scratch/                 # Utility scripts & test verification suites
```

---

## 🔧 Setup & Environment Configuration

### Prerequisites
* Python 3.10+
* Docker & Docker Compose (for containerized deployment)
* MongoDB Atlas Cluster URI
* PJSIP build dependencies (included in Dockerfile)

### `.env` Key Reference

```env
# General
COMPANY_NAME="Chauwk"
SALES_BOT_NAME="Zara"
SERVER_HOST=0.0.0.0
SERVER_PORT=5000

# Engine Selector ('modular' or 'realtime')
VOICE_BOT_MODE=modular

# Emergency Safety Flag
DISABLE_AI_ENGINES=false

# API Keys
OPENAI_API_KEY=sk-proj-...
DEEPGRAM_API_KEY=a8a3507d...
GEMINI_API_KEY=AQ.Ab8RN6...
SARVAM_API_KEY=sk_8ht8c19y...

# Modular Pipeline Settings
DEEPGRAM_MODEL=nova-2-phonecall
GEMINI_MODEL=gemini-2.5-flash
SARVAM_MODEL=bulbul:v3
SARVAM_SPEAKER=neha
SARVAM_LANGUAGE_CODE=en-IN

# SIP / Exotel Telephony
USE_SIP_TRUNK=true
INBOUND_SIP_ENABLED=true
SIP_PUBLIC_IP=3.111.29.229
SIP_SERVER_PORT=5060
EXOTEL_ACCOUNT_SID=chauwk1m
EXOTEL_API_KEY=f55adc46...
EXOTEL_API_TOKEN=b29310a6...
EXOTEL_FROM_NUMBER=04040377112
EXOTEL_SUBDOMAIN=api.in.exotel.com

# SMTP Email (Zoho)
SMTP_HOST=smtp.zoho.in
SMTP_PORT=465
SMTP_USER=hello@chauwk.com
SMTP_PASSWORD=...
SMTP_FROM_NAME="Chauwk Sales Team"
SMTP_FROM_EMAIL=hello@chauwk.com

# Database & Storage
DB_URL="mongodb+srv://chauwk:chauwk123@cluster0.phrdp.mongodb.net/chauwk?retryWrites=true&w=majority"
AWS_ACCESS_KEY_ID=AKIA5P4...
AWS_SECRET_ACCESS_KEY=4SQ+cm...
AWS_DEFAULT_REGION=ap-south-1
AWS_S3_BUCKET_NAME=chauwk-aivoiceagent-stream
```

---

## 🐳 Docker Deployment

To build and run the complete containerized stack on host:

```bash
# Clone repository
git clone https://github.com/Chauwk/Agent-Stream-Voice-Agent.git
cd Agent-Stream-Voice-Agent

# Configure environment variables
cp env.example .env

# Build and start container services
sudo docker compose up -d --build
```

---

## 📑 API Documentation & Web UI

Once the application is running, access the interactive documentation and web management portal:

* **Swagger UI Docs**: `http://<your-host-ip>:5000/docs`
* **ReDoc API Specs**: `http://<your-host-ip>:5000/redoc`
* **Health Check**: `http://<your-host-ip>:5000/health`
* **Web Portal & Voice Dashboard**: `http://<your-host-ip>:5000/`

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.