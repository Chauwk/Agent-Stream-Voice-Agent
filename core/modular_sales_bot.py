#!/usr/bin/env python3
"""
Modular Voice Bot Client using Deepgram (STT), Gemini (LLM), and Sarvam AI (TTS)
Acts as a drop-in replacement for OpenAIRealtimeSalesBot when VOICE_BOT_MODE is set to 'modular'.
"""

import asyncio
import json
import logging
import time
import base64
import websockets
from google import genai
from sarvamai import SarvamAI, AsyncSarvamAI
from config import Config
from websockets.connection import State

logger = logging.getLogger(__name__)

class ModularSalesBot:
    """Modular Voice AI bot integrating Deepgram, Gemini, and Sarvam AI with PJSIP telephony"""
    
    def __init__(self):
        self.default_sample_rate = Config.DEFAULT_SAMPLE_RATE
        self.sip_server = None
        
        # Connections state map: call_id -> session state
        self.connections = {}
        
        # Initialize Sarvam Clients
        self.sync_sarvam_client = SarvamAI(api_subscription_key=Config.SARVAM_API_KEY)
        self.sarvam_client = AsyncSarvamAI(api_subscription_key=Config.SARVAM_API_KEY)
        
        # Pre-generate default greeting audio at startup
        self.cached_greeting_text = f"Hello! Thank you for calling {Config.COMPANY_NAME}. How can I help you today?"
        self.cached_greeting_audio = None
        self.cached_speaker = Config.SARVAM_SPEAKER
        self.cached_company = Config.COMPANY_NAME
        self.cached_language = Config.SARVAM_LANGUAGE_CODE
        
        try:
            logger.info("⏳ Pre-generating and caching startup greeting audio...")
            kwargs = {
                "text": self.cached_greeting_text,
                "target_language_code": Config.SARVAM_LANGUAGE_CODE,
                "speaker": Config.SARVAM_SPEAKER,
                "model": Config.SARVAM_MODEL,
                "output_audio_codec": "linear16",
                "speech_sample_rate": 16000
            }
            pace = getattr(Config, "SARVAM_PACE", 1.15)
            if pace is not None:
                kwargs["pace"] = pace
            pitch = getattr(Config, "SARVAM_PITCH", 0.0)
            if pitch is not None and pitch != 0.0 and "bulbul:v3" not in Config.SARVAM_MODEL:
                kwargs["pitch"] = pitch
                
            response = self.sync_sarvam_client.text_to_speech.convert(**kwargs)
            if response and response.audios:
                base64_audio = response.audios[0]
                self.cached_greeting_audio = base64.b64decode(base64_audio)
                logger.info("✅ Startup greeting audio cached successfully!")
            else:
                logger.error("❌ Failed to cache greeting: Empty response from Sarvam")
        except Exception as e:
            logger.error(f"❌ Failed to pre-generate greeting: {e}")
            
        # Initialize Gemini Client once to avoid cold starts on first call
        self.gemini_client = None
        try:
            import os
            gcp_key = os.getenv('GCP_SERVICE_ACCOUNT_KEY') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            
            # Autodetect in root directory if not specified in env
            if not gcp_key:
                for f in os.listdir('.'):
                    if f.endswith('.json') and f.startswith('project-'):
                        gcp_key = f
                        break
                        
            if gcp_key and os.path.exists(gcp_key):
                logger.info(f"🔑 Pre-configuring Gemini Client with GCP Service Account (Vertex AI): {gcp_key}")
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(
                    gcp_key,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                with open(gcp_key, 'r') as f:
                    key_data = json.load(f)
                project_id = key_data.get('project_id')
                
                self.gemini_client = genai.Client(
                    vertexai=True,
                    project=project_id,
                    location="asia-south1",
                    credentials=creds
                )
            else:
                logger.info("🔑 Pre-configuring Gemini Client with API Key (AI Studio)")
                self.gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
                
            self.gemini_warmed_up = False
        except Exception as e:
            logger.error(f"❌ Failed to pre-configure Gemini client: {e}")
            
        logger.info("🤖 Modular Voice Bot Engine Initialized")
        logger.info(f"   🎙️ STT Model (Deepgram): {Config.DEEPGRAM_MODEL}")
        logger.info(f"   🧠 LLM Model (Gemini): {Config.GEMINI_MODEL}")
        logger.info(f"   🔊 TTS Model (Sarvam): {Config.SARVAM_MODEL}")
        logger.info(f"   🎭 Speaker (Sarvam): {Config.SARVAM_SPEAKER}")
        logger.info(f"   🌐 Language (Sarvam): {Config.SARVAM_LANGUAGE_CODE}")

    async def _warmup_gemini(self):
        """Warms up the Gemini client connection to eliminate first-call cold-start latency"""
        try:
            logger.info("🧠 Warming up Gemini Client connection...")
            await self.gemini_client.aio.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents="ping"
            )
            logger.info("🧠 Gemini Client warmed up successfully.")
        except Exception as e:
            logger.warning(f"⚠️ Gemini Client warmup failed (will retry on first call): {e}")

    async def start_server(self):
        """Start SIP server for direct Exotel SIP trunking"""
        # Run Gemini warmup task now that the event loop is running
        if not getattr(self, "gemini_warmed_up", False) and self.gemini_client:
            asyncio.create_task(self._warmup_gemini())
            
        try:
            logger.info(f'🚀 Starting SIP Server (Modular Mode) on {Config.SIP_SERVER_HOST}:{Config.SIP_SERVER_PORT}')
            logger.info('📞 Ready for direct Exotel SIP trunk connections!')
            logger.info(f'🏢 Company: {Config.COMPANY_NAME}')
            logger.info(f'🤖 Bot Name: {Config.SALES_BOT_NAME}')
            
            # Import SIP server
            from core.sip_server import SIPServer
            
            # Create and start SIP server, passing self as the bot reference
            self.sip_server = SIPServer(openai_bot=self)
            
            # Initialize PJSUA SIP stack
            logger.info("⏳ Initializing PJSUA2 SIP stack...")
            self.sip_server.initialize_pjsua()
            
            # Start SIP server
            await self.sip_server.start()
            
            logger.info(f'✅ SIP Server running at sip://{Config.SIP_SERVER_HOST}:{Config.SIP_SERVER_PORT}')
            logger.info('📞 Waiting for incoming SIP calls...')
            
            # Keep running forever
            await asyncio.Future()
            
        except Exception as e:
            logger.error(f'❌ SIP Server Error: {e}')
            raise
        finally:
            if self.sip_server:
                await self.sip_server.stop()

    async def _check_and_update_greeting(self):
        """Regenerate greeting audio asynchronously if configuration has changed"""
        current_text = f"Hello! Thank you for calling {Config.COMPANY_NAME}. How can I help you today?"
        if (self.cached_greeting_audio is None or 
            self.cached_speaker != Config.SARVAM_SPEAKER or
            self.cached_company != Config.COMPANY_NAME or
            self.cached_language != Config.SARVAM_LANGUAGE_CODE or
            self.cached_greeting_text != current_text):
            
            logger.info(f"🔄 Dynamic Voice Config changed! Regenerating greeting audio for speaker '{Config.SARVAM_SPEAKER}'...")
            try:
                kwargs = {
                    "text": current_text,
                    "target_language_code": Config.SARVAM_LANGUAGE_CODE,
                    "speaker": Config.SARVAM_SPEAKER,
                    "model": Config.SARVAM_MODEL,
                    "output_audio_codec": "linear16",
                    "speech_sample_rate": 16000
                }
                pace = getattr(Config, "SARVAM_PACE", 1.15)
                if pace is not None:
                    kwargs["pace"] = pace
                pitch = getattr(Config, "SARVAM_PITCH", 0.0)
                if pitch is not None and pitch != 0.0 and "bulbul:v3" not in Config.SARVAM_MODEL:
                    kwargs["pitch"] = pitch
                    
                response = await self.sarvam_client.text_to_speech.convert(**kwargs)
                if response and response.audios:
                    base64_audio = response.audios[0]
                    self.cached_greeting_audio = base64.b64decode(base64_audio)
                    self.cached_greeting_text = current_text
                    self.cached_speaker = Config.SARVAM_SPEAKER
                    self.cached_company = Config.COMPANY_NAME
                    self.cached_language = Config.SARVAM_LANGUAGE_CODE
                    logger.info(f"✅ Dynamic greeting audio regenerated successfully for {Config.SARVAM_SPEAKER}!")
                else:
                    logger.error("❌ Failed to regenerate greeting: Empty response from Sarvam")
            except Exception as e:
                logger.error(f"❌ Failed to regenerate greeting audio: {e}")

    async def connect_to_openai_enhanced(self, call_id: str):
        """
        Setup modular connection endpoints (Deepgram, Gemini, Sarvam) for the call session.
        Method name matches the SIP server interface call for backward compatibility.
        """
        logger.info(f"🔗 INITIALIZING MODULAR PIPELINE for call: {call_id}")
        
        # Ensure Gemini warmup runs if it hasn't completed yet
        if not getattr(self, "gemini_warmed_up", False) and self.gemini_client:
            asyncio.create_task(self._warmup_gemini())
            
        # 0. Regenerate greeting audio if config was dynamically updated
        await self._check_and_update_greeting()
        
        # 1. Prepare system instruction, safety settings, and history
        try:
            # Define the end_call tool closure
            async def end_call() -> str:
                """Hang up the call when the conversation is finished, the customer says goodbye, or they want to end the call."""
                logger.info(f"📞 Tool end_call invoked for call: {call_id}")
                asyncio.create_task(self.delayed_hangup(call_id))
                return "Call hangup initiated"

            # Format company products/services for prompt injection
            products_summary = "; ".join([f"{p['name']} at {p['price']} ({p['description']})" for p in Config.PRODUCTS])

            system_instruction = (
                f"You are {Config.SALES_BOT_NAME}, sales rep for {Config.COMPANY_NAME}. Speak EXCLUSIVELY in English.\n"
                "Strict Rules:\n"
                "- Keep responses concise, under 25 words per sentence, and max 60 words total. No lists/markdown.\n"
                f"- Only sell these standard services: {products_summary}. Reject custom deals/discounts.\n"
                "- Decline off-topic queries (coding, math, politics) and steer back to Chauwk sales.\n"
                "- Never praise or mention competitors.\n"
                "- Call the end_call tool to hang up ONLY when the customer explicitly says goodbye or requests to hang up/end the call (e.g. 'goodbye', 'bye', 'hang up', 'end the call'). Do NOT call the end_call tool for product selections, questions, or vague inputs.\n"
                "- When the call is ending, make sure to state a warm goodbye (e.g., 'Thank you for calling. Goodbye!') first, and then call the end_call tool to hang up."
            )
            
            from google.genai import types
            history = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="A customer just called our sales line. Please greet them warmly and ask how you can help them today.")]
                ),
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=self.cached_greeting_text)]
                )
            ]
            
            safety_settings = [
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                )
            ]
        except Exception as e:
            logger.error(f"❌ Failed to configure Gemini parameters: {e}")
            raise
            
        # 2. Establish session state structure
        self.connections[call_id] = {
            "history": history,
            "system_instruction": system_instruction,
            "safety_settings": safety_settings,
            "end_call_tool": end_call,
            "deepgram_ws": None,
            "sarvam_ws": None,
            "reconnect_event": asyncio.Event(),
            "tasks": [],
            "user_speaking": False,
            "is_bot_speaking": False,
            "current_context_id": None,
            "llm_queue": asyncio.Queue(),  # Queue to pass text prompts to LLM
            "tts_queue": asyncio.Queue(),  # Queue to pass text chunks to TTS
            "current_llm_task": None,      # Active Gemini generation task
            "current_tts_task": None,      # Active TTS API task
            "consecutive_speech_frames": 0,
            "consecutive_silence_frames": 0,
            "local_user_speaking": False,
            "start_time": time.time()      # Track startup time for startup guard
        }
        
        # 3. Play greeting instantly from cache (non-blocking) to eliminate greeting delay for the caller
        if self.cached_greeting_audio:
            logger.info(f"🗣️ Playing cached greeting for call: {call_id}")
            if self.sip_server:
                asyncio.create_task(self.sip_server.send_audio_to_rtp(call_id, self.cached_greeting_audio))

        # 4. Connect to WebSockets
        try:
            await self._connect_websockets(call_id)
            logger.info(f"✅ Deepgram WebSocket connected for call: {call_id}")
            
            session_state = self.connections[call_id]
            
            # Start background async pipeline workers
            dg_task = asyncio.create_task(self._handle_deepgram_responses(call_id))
            tts_process_task = asyncio.create_task(self._process_tts_queue(call_id))
            llm_process_task = asyncio.create_task(self._process_llm_queue(call_id))
            dg_keepalive_task = asyncio.create_task(self._send_deepgram_keepalives(call_id))
            sarvam_ws_task = asyncio.create_task(self._run_sarvam_websocket_loop(call_id))
            silence_task = asyncio.create_task(self._silence_monitor_loop(call_id))
            
            session_state["tasks"].extend([dg_task, tts_process_task, llm_process_task, dg_keepalive_task, sarvam_ws_task, silence_task])
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize modular pipeline sockets: {e}")
            await self.cleanup_connections(call_id)
            raise

    async def _connect_websockets(self, call_id: str):
        """Connect to Deepgram WebSocket"""
        session_state = self.connections[call_id]
        
        # Deepgram Live WS config - boost company and bot name keywords
        endpointing_ms = getattr(Config, "DEEPGRAM_ENDPOINTING", 300)
        dg_url = f"wss://api.deepgram.com/v1/listen?model={Config.DEEPGRAM_MODEL}&encoding=linear16&sample_rate=16000&channels=1&endpointing={endpointing_ms}&vad_events=true&interim_results=false&keywords=Chauwk:4.0&keywords=Sarah:2.0"
        dg_headers = {"Authorization": f"Token {Config.DEEPGRAM_API_KEY}"}
        
        import inspect
        connect_params = inspect.signature(websockets.connect).parameters
        connect_kwargs = {}
        if "additional_headers" in connect_params:
            connect_kwargs["additional_headers"] = dg_headers
        else:
            connect_kwargs["extra_headers"] = dg_headers
            
        dg_ws = await websockets.connect(dg_url, **connect_kwargs)
        session_state["deepgram_ws"] = dg_ws

    async def send_audio_to_openai(self, call_id: str, audio_chunk: bytes, sample_rate: int = 16000):
        """
        Accepts raw PCM16 audio from the caller call and streams it to Deepgram.
        Method name matches the SIP server interface call for backward compatibility.
        """
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        # Apply local noise gate and track sustained speech/silence to trigger precise local VAD
        count = len(audio_chunk) // 2
        rms = 0.0
        if count > 0:
            import struct
            import math
            # Unpack 16-bit little-endian samples
            samples = struct.unpack(f"<{count}h", audio_chunk)
            sum_squares = sum(s * s for s in samples)
            rms = math.sqrt(sum_squares / count)
            
        # Initialize local VAD counters if not present
        if "consecutive_speech_frames" not in session_state:
            session_state["consecutive_speech_frames"] = 0
            session_state["consecutive_silence_frames"] = 0
            session_state["local_user_speaking"] = False
            
        # Check for startup guard: ignore VAD during the first 1.5 seconds of the call to prevent initial line clicks/noises from triggering interruptions or breaking initial states
        call_age = time.time() - session_state.get("start_time", time.time())
        is_startup_guard_active = call_age < 1.5

        # Update VAD state based on RMS threshold
        # Default threshold of 1500.0 is ideal for telephony lines to gate hum/breaths and prevent false interruptions
        vad_threshold = getattr(Config, "VAD_RMS_THRESHOLD", 1500.0)

        if is_startup_guard_active:
            # Force VAD state to silent during startup guard to avoid early transients setting user_speaking=True or triggering interruptions
            session_state["consecutive_speech_frames"] = 0
            session_state["consecutive_silence_frames"] += 1
            audio_chunk = b"\x00" * len(audio_chunk)
        elif rms >= vad_threshold:
            session_state["consecutive_speech_frames"] += 1
            session_state["consecutive_silence_frames"] = 0
            
            # If we detect sustained speech (e.g., 8 consecutive frames = 160ms)
            if session_state["consecutive_speech_frames"] >= 8 and not session_state["local_user_speaking"]:
                session_state["local_user_speaking"] = True
                session_state["user_speaking"] = True
                
                if self.is_bot_actively_speaking(call_id):
                    logger.info(f"🎤 LOCAL VAD: CUSTOMER STARTED SPEAKING (Interruption - IGNORED local VAD to prevent self-interruption/echo) for call {call_id} (RMS={rms:.1f})")
                    # Do NOT call self._handle_customer_interruption(call_id) here.
                    # Rely on Deepgram word transcription for precise barge-in.
                else:
                    logger.info(f"🎤 LOCAL VAD: CUSTOMER STARTED SPEAKING (Bot is silent) for call {call_id} (RMS={rms:.1f})")
        else:
            session_state["consecutive_silence_frames"] += 1
            session_state["consecutive_speech_frames"] = 0
            
            # If we detect sustained silence (e.g., 20 consecutive frames = 400ms)
            if session_state["consecutive_silence_frames"] >= 20 and session_state["local_user_speaking"]:
                session_state["local_user_speaking"] = False
                session_state["user_speaking"] = False
                logger.info(f"🎤 LOCAL VAD: CUSTOMER STOPPED SPEAKING for call {call_id}")
                
            # Do NOT replace audio chunk with silence here anymore, send raw audio to Deepgram!
            # audio_chunk = b"\x00" * len(audio_chunk)
            
        # Track chunk sending activity to verify PJSIP/Exotel audio stream is active
        if not hasattr(self, "_chunk_stats"):
            self._chunk_stats = {}
        if call_id not in self._chunk_stats:
            self._chunk_stats[call_id] = 0
            logger.info(f"DEBUG: Started receiving audio chunks from PJSIP for call {call_id}")
            
        self._chunk_stats[call_id] += 1
        if self._chunk_stats[call_id] % 100 == 0:
            logger.info(f"DEBUG: Sent {self._chunk_stats[call_id]} audio chunks to Deepgram for call {call_id}")
            
        dg_ws = session_state.get("deepgram_ws")
        if dg_ws and dg_ws.state == State.OPEN:
            try:
                # Direct binary send of PCM16 data to Deepgram
                await dg_ws.send(audio_chunk)
            except Exception as e:
                logger.error(f"❌ Error sending audio chunk to Deepgram for call {call_id}: {e}")

    async def _handle_deepgram_responses(self, call_id: str):
        """Receives and processes transcription events from Deepgram"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        dg_ws = session_state["deepgram_ws"]
        try:
            async for message in dg_ws:
                data = json.loads(message)
                
                # Check for speech detection events (log only, rely on local VAD for interruptions)
                is_final = data.get("is_final", False)
                speech_started = (data.get("type") == "SpeechStarted")
                speech_ended = (data.get("type") == "SpeechEnded")
                
                if speech_started:
                    logger.info(f"🎤 DEEPGRAM VAD: SpeechStarted for call {call_id}")
                    session_state["user_speaking"] = True
                    session_state["user_speaking_start_time"] = time.time()
                    # We rely on final transcripts (real words spoken) for barge-in rather than raw VAD SpeechStarted
                    # to completely protect the bot from being cut off by line clicks, breaths, background noise, or echo.
                    
                if speech_ended:
                    logger.info(f"🎤 DEEPGRAM VAD: SpeechEnded for call {call_id}")
                    session_state["user_speaking"] = False
                    if "user_speaking_start_time" in session_state:
                        try:
                            del session_state["user_speaking_start_time"]
                        except KeyError:
                            pass
                    session_state["user_speaking"] = False
                
                channel = data.get("channel", {})
                if isinstance(channel, dict):
                    alternatives = channel.get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        if transcript.strip() and is_final:
                            logger.info(f"🎤 CUSTOMER SAID: {transcript}")
                            
                            # Invalidate and cancel previous speaking/thinking tasks
                            await self._handle_customer_interruption(call_id)
                            
                            session_state["user_speaking"] = False
                            if "user_speaking_start_time" in session_state:
                                try:
                                    del session_state["user_speaking_start_time"]
                                except KeyError:
                                    pass
                            
                            # Reset local VAD states upon successful transcription
                            session_state["consecutive_speech_frames"] = 0
                            session_state["consecutive_silence_frames"] = 20
                            session_state["local_user_speaking"] = False
                            
                            # Forward transcription text to the LLM processor queue
                            await session_state["llm_queue"].put(transcript)
                        
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"🔌 Deepgram connection closed for call {call_id}: code={e.code}, reason='{e.reason}'")
        except Exception as e:
            logger.error(f"❌ Error handling Deepgram messages for call {call_id}: {e}", exc_info=True)

    async def _send_deepgram_keepalives(self, call_id: str):
        """Sends periodic KeepAlive messages to Deepgram to prevent inactivity timeouts"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        try:
            while True:
                await asyncio.sleep(4)
                session_state = self.connections.get(call_id)
                if not session_state:
                    break
                dg_ws = session_state.get("deepgram_ws")
                if dg_ws and dg_ws.state == State.OPEN:
                    logger.info(f"⏳ Sending KeepAlive to Deepgram for call {call_id}")
                    await dg_ws.send(json.dumps({"type": "KeepAlive"}))
                else:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"❌ Error sending Deepgram KeepAlive: {e}")

    async def _process_llm_queue(self, call_id: str):
        """Listens for user transcripts, queries Gemini, and pushes sentence blocks to the TTS queue"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        history = session_state["history"]
        system_instruction = session_state["system_instruction"]
        safety_settings = session_state["safety_settings"]
        end_call = session_state["end_call_tool"]
        llm_queue = session_state["llm_queue"]
        tts_queue = session_state["tts_queue"]
        
        try:
            while True:
                prompt = await llm_queue.get()
                logger.info(f"🧠 Querying Gemini LLM with: '{prompt}'")
                
                # Append user prompt to manual history list
                from google.genai import types
                history.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)]
                    )
                )
                
                session_state["is_bot_speaking"] = True
                # Set a unique context ID for this speech turn
                context_id = f"ctx_{int(time.time() * 1000)}"
                session_state["current_context_id"] = context_id
                
                generated_text = ""
                start_query_time = time.time()
                
                # Inner function to stream Gemini response and parse sentences
                async def run_gemini():
                    nonlocal generated_text
                    try:
                        # Call generate_content_stream using the shared client
                        response = await self.gemini_client.aio.models.generate_content_stream(
                            model=Config.GEMINI_MODEL,
                            contents=history,
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction,
                                tools=[end_call],
                                safety_settings=safety_settings
                            )
                        )
                        current_sentence = ""
                        first_chunk = True
                        
                        async for chunk in response:
                            if first_chunk:
                                logger.info(f"🧠 Gemini LLM first chunk received in {time.time() - start_query_time:.3f}s")
                                first_chunk = False
                            text_delta = chunk.text
                            if text_delta:
                                generated_text += text_delta
                                current_sentence += text_delta
                                
                                # Split by sentence boundaries (., ?, !, \n) or clause boundaries (,, ;)
                                while True:
                                    idx = -1
                                    punctuations = ['.', '?', '!', '\n', ',', ';']
                                    for p in punctuations:
                                        p_idx = current_sentence.find(p)
                                        if p_idx != -1:
                                            if idx == -1 or p_idx < idx:
                                                idx = p_idx
                                                
                                    if idx == -1:
                                        break
                                        
                                    split_char = current_sentence[idx]
                                    chunk_candidate = current_sentence[:idx+1].strip()
                                    
                                    # For commas or semicolons, enforce a minimum length threshold to avoid tiny fragments
                                    if split_char in [',', ';']:
                                        words = chunk_candidate.split()
                                        if len(words) < 3 or len(chunk_candidate) < 15:
                                            next_idx = -1
                                            for p in punctuations:
                                                p_idx = current_sentence.find(p, idx + 1)
                                                if p_idx != -1:
                                                    if next_idx == -1 or p_idx < next_idx:
                                                        next_idx = p_idx
                                            if next_idx != -1:
                                                idx = next_idx
                                                split_char = current_sentence[idx]
                                                chunk_candidate = current_sentence[:idx+1].strip()
                                            else:
                                                break
                                                
                                    sentence_to_send = current_sentence[:idx+1].strip()
                                    current_sentence = current_sentence[idx+1:]
                                    
                                    if sentence_to_send:
                                        await tts_queue.put((context_id, sentence_to_send))
                                        
                        if current_sentence.strip():
                            await tts_queue.put((context_id, current_sentence.strip()))
                    except Exception as e:
                        logger.error(f"❌ Gemini generation error inside task: {e}")
                        raise

                llm_task = asyncio.create_task(run_gemini())
                session_state["current_llm_task"] = llm_task
                
                try:
                    await llm_task
                    # Append completed response to history
                    if generated_text.strip():
                        history.append(
                            types.Content(
                                role="model",
                                parts=[types.Part.from_text(text=generated_text.strip())]
                            )
                        )
                except asyncio.CancelledError:
                    logger.info(f"🧠 Gemini generation task was cancelled for context: {context_id}")
                    # If cancelled/interrupted, append the partial response so model knows what it said
                    if generated_text.strip():
                        history.append(
                            types.Content(
                                role="model",
                                parts=[types.Part.from_text(text=generated_text.strip())]
                            )
                        )
                except Exception as e:
                    logger.error(f"❌ Gemini generation task failed: {e}")
                finally:
                    session_state["current_llm_task"] = None
                    llm_queue.task_done()
                    
        except asyncio.CancelledError:
            pass

    async def _run_sarvam_websocket_loop(self, call_id: str):
        """Manages a persistent connection to the Sarvam AI TTS WebSocket"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        logger.info(f"🔊 Starting persistent Sarvam AI WebSocket connection manager for call {call_id}...")
        
        while True:
            # Check if session is still active
            session_state = self.connections.get(call_id)
            if not session_state:
                break
                
            try:
                logger.info(f"🔊 Connecting to Sarvam AI TTS WebSocket (model bulbul:v3) for call {call_id}...")
                async with self.sarvam_client.text_to_speech_streaming.connect(
                    model=Config.SARVAM_MODEL,
                    send_completion_event="true"
                ) as socket_client:
                    logger.info(f"🔊 Configuring Sarvam AI TTS WebSocket for call {call_id}...")
                    kwargs = {
                        "target_language_code": Config.SARVAM_LANGUAGE_CODE,
                        "speaker": Config.SARVAM_SPEAKER,
                        "speech_sample_rate": 16000,
                        "output_audio_codec": "linear16"
                    }
                    pace = getattr(Config, "SARVAM_PACE", 1.15)
                    if pace is not None:
                        kwargs["pace"] = pace
                    pitch = getattr(Config, "SARVAM_PITCH", 0.0)
                    if pitch is not None and pitch != 0.0 and "bulbul:v3" not in Config.SARVAM_MODEL:
                        kwargs["pitch"] = pitch
                        
                    await socket_client.configure(**kwargs)
                    
                    session_state["sarvam_ws"] = socket_client
                    logger.info(f"🔊 Sarvam AI WebSocket is ready for call {call_id}.")
                    
                    # Connection keep-alive ping loop
                    while True:
                        reconnect_event = session_state.get("reconnect_event")
                        if reconnect_event:
                            reconnect_event.clear()
                            
                        try:
                            # Wait for reconnect event or timeout (20s keep-alive)
                            if reconnect_event:
                                await asyncio.wait_for(reconnect_event.wait(), timeout=20.0)
                                logger.info(f"🔊 Reconnect event triggered for call {call_id}. Reconnecting immediately...")
                                break
                            else:
                                await asyncio.sleep(20)
                        except asyncio.TimeoutError:
                            # Timeout passed, proceed to send keep-alive ping
                            pass
                            
                        session_state = self.connections.get(call_id)
                        if not session_state or session_state.get("sarvam_ws") != socket_client:
                            break
                        if not socket_client._websocket.open:
                            break
                            
                        # Send ping
                        try:
                            await socket_client.ping()
                        except Exception as ping_err:
                            logger.error(f"❌ Error pinging Sarvam WebSocket: {ping_err}")
                            break
                            
            except asyncio.CancelledError:
                logger.info(f"🔊 Sarvam AI WebSocket loop cancelled for call {call_id}")
                break
            except Exception as e:
                logger.error(f"❌ Sarvam AI WebSocket connection error for call {call_id}: {e}")
                
             # Clear socket in session if connection failed/closed
            session_state = self.connections.get(call_id)
            is_interrupted = False
            if session_state:
                if session_state.get("sarvam_ws") is not None:
                    session_state["sarvam_ws"] = None
                reconnect_event = session_state.get("reconnect_event")
                if reconnect_event and reconnect_event.is_set():
                    is_interrupted = True
                    reconnect_event.clear()
                    
            if not is_interrupted:
                # Wait 1.5 seconds before retrying connection (backoff for failures only)
                await asyncio.sleep(1.5)
            else:
                logger.info(f"🔊 Reconnecting to Sarvam TTS immediately (0ms delay) after interruption for call {call_id}.")

    async def _process_tts_queue(self, call_id: str):
        """Listens for sentences and invokes Sarvam AI TTS asynchronously (supports WebSocket-streaming)"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        tts_queue = session_state["tts_queue"]
        
        try:
            while True:
                context_id, sentence_text = await tts_queue.get()
                
                # Check if this context has been cancelled/interrupted
                if context_id != session_state["current_context_id"]:
                    tts_queue.task_done()
                    continue
                
                if not sentence_text or not sentence_text.strip():
                    tts_queue.task_done()
                    continue
                
                logger.info(f"🔊 Processing TTS for sentence: '{sentence_text}'")
                
                # Attempt to get Sarvam WebSocket connection
                sarvam_ws = session_state.get("sarvam_ws")
                if not sarvam_ws or not sarvam_ws._websocket.open:
                    logger.info("⏳ Sarvam WebSocket not ready. Waiting for connection...")
                    for _ in range(10): # Wait up to 1.0 second
                        await asyncio.sleep(0.1)
                        # Check context invalidation during wait
                        if context_id != session_state["current_context_id"]:
                            break
                        sarvam_ws = session_state.get("sarvam_ws")
                        if sarvam_ws and sarvam_ws._websocket.open:
                            break
                
                # Fallback to HTTP POST TTS if WebSocket is not ready
                if not sarvam_ws or not sarvam_ws._websocket.open or context_id != session_state["current_context_id"]:
                    if context_id != session_state["current_context_id"]:
                        tts_queue.task_done()
                        continue
                        
                    logger.warning("⚠️ Sarvam WebSocket not available. Falling back to HTTP TTS.")
                    try:
                        kwargs = {
                            "text": sentence_text,
                            "target_language_code": Config.SARVAM_LANGUAGE_CODE,
                            "speaker": Config.SARVAM_SPEAKER,
                            "model": Config.SARVAM_MODEL,
                            "output_audio_codec": "linear16",
                            "speech_sample_rate": 16000
                        }
                        pace = getattr(Config, "SARVAM_PACE", 1.15)
                        if pace is not None:
                            kwargs["pace"] = pace
                        pitch = getattr(Config, "SARVAM_PITCH", 0.0)
                        if pitch is not None and pitch != 0.0 and "bulbul:v3" not in Config.SARVAM_MODEL:
                            kwargs["pitch"] = pitch
                            
                        tts_coro = self.sarvam_client.text_to_speech.convert(**kwargs)
                        tts_task = asyncio.create_task(tts_coro)
                        session_state["current_tts_task"] = tts_task
                        
                        response = await tts_task
                        
                        if context_id != session_state["current_context_id"]:
                            logger.info(f"🚫 Context changed during HTTP TTS. Discarding output.")
                            continue
                            
                        if response and response.audios:
                            base64_audio = response.audios[0]
                            pcm_audio = base64.b64decode(base64_audio)
                            logger.info(f"🗣️ SARAH SPEAKING (HTTP): {sentence_text}")
                            if self.sip_server:
                                await self.sip_server.send_audio_to_rtp(call_id, pcm_audio)
                        else:
                            logger.error(f"❌ Empty response from HTTP TTS for: '{sentence_text}'")
                    except asyncio.CancelledError:
                        logger.info(f"🚫 HTTP TTS task cancelled for context: {context_id}")
                    except Exception as e:
                        logger.error(f"❌ HTTP TTS failed: {e}")
                    finally:
                        session_state["current_tts_task"] = None
                        tts_queue.task_done()
                    continue
                
                # If we get here, WebSocket is available!
                try:
                    async def run_websocket_tts():
                        # Send text chunks
                        await sarvam_ws.convert(sentence_text)
                        await sarvam_ws.flush()
                        
                        # Receive and stream back audio chunks
                        logger.info(f"🗣️ SARAH SPEAKING (WS Streaming): {sentence_text}")
                        while True:
                            response = await sarvam_ws.recv()
                            
                            # Verify context hasn't changed
                            if context_id != session_state["current_context_id"]:
                                break
                                
                            if response.type == 'audio':
                                base64_audio = response.data.audio
                                pcm_audio = base64.b64decode(base64_audio)
                                if self.sip_server:
                                    await self.sip_server.send_audio_to_rtp(call_id, pcm_audio)
                            elif response.type == 'event':
                                if getattr(response.data, 'event_type', None) == 'final':
                                    break
                            elif response.type == 'error':
                                logger.error(f"❌ Error response from Sarvam WS: {response.data}")
                                break
                                
                    tts_task = asyncio.create_task(run_websocket_tts())
                    session_state["current_tts_task"] = tts_task
                    
                    await tts_task
                    
                except asyncio.CancelledError:
                    logger.info(f"🚫 WS TTS task cancelled for context: {context_id}")
                except Exception as e:
                    logger.error(f"❌ WS TTS failed: {e}")
                    # Invalidate WS so next turn reconnects
                    session_state["sarvam_ws"] = None
                finally:
                    session_state["current_tts_task"] = None
                    tts_queue.task_done()
                    
        except asyncio.CancelledError:
            pass

    def is_bot_actively_speaking(self, call_id: str) -> bool:
        """Checks if the bot is currently speaking (playing audio) or actively synthesizing speech"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return False
            
        # 1. Check if TTS synthesis task is active
        active_tts = session_state.get("current_tts_task")
        if active_tts and not active_tts.done():
            return True
            
        # 2. Check if TTS queue has items pending
        tts_q = session_state.get("tts_queue")
        if tts_q and not tts_q.empty():
            return True
            
        # 3. Check if SIP playout buffer has active audio playing
        if self.sip_server:
            call_state = self.sip_server.sip_calls.get(call_id)
            if call_state and hasattr(call_state, "playback_buffer") and len(call_state.playback_buffer) > 0:
                return True
                
        return False

    async def _handle_customer_interruption(self, call_id: str):
        """Immediately stops bot speaking and cancels active Gemini/TTS requests on customer interruption"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        logger.info(f"⚡ INTERRUPTING BOT for call {call_id}")
        
        # 1. Invalidate current context
        session_state["current_context_id"] = None
        session_state["is_bot_speaking"] = False
        
        # 2. Cancel active LLM task immediately
        active_llm = session_state.get("current_llm_task")
        if active_llm and not active_llm.done():
            active_llm.cancel()
            logger.info(f"🚫 Active LLM task cancelled for call {call_id}")
            
        # 3. Cancel active TTS task immediately
        active_tts = session_state.get("current_tts_task")
        if active_tts and not active_tts.done():
            active_tts.cancel()
            logger.info(f"🚫 Active TTS task cancelled for call {call_id}")
            
        # 4. Close active Sarvam WebSocket to discard server-buffered audio
        sarvam_ws = session_state.get("sarvam_ws")
        if sarvam_ws and hasattr(sarvam_ws, "_websocket") and sarvam_ws._websocket.open:
            try:
                # Run the close asynchronously in a non-blocking way
                asyncio.create_task(sarvam_ws._websocket.close())
                logger.info(f"🔇 Active Sarvam WebSocket closed on interruption for call {call_id}")
            except Exception as e:
                logger.debug(f"Error closing Sarvam WS on interruption: {e}")
                
        # Trigger instant reconnection of the manager loop
        reconnect_event = session_state.get("reconnect_event")
        if reconnect_event:
            reconnect_event.set()
        
        # 5. Flush PJSIP playout buffer
        if self.sip_server:
            call_state = self.sip_server.sip_calls.get(call_id)
            if call_state:
                call_state.playback_buffer = b""
                call_state.is_playing = False
                logger.info(f"🔇 SIP playout buffer cleared for call {call_id}")
                
        # 6. Clear pending TTS queue
        while not session_state["tts_queue"].empty():
            try:
                session_state["tts_queue"].get_nowait()
                session_state["tts_queue"].task_done()
            except asyncio.QueueEmpty:
                break

    async def _silence_monitor_loop(self, call_id: str):
        """Monitors caller silence and injects follow-up prompts if inactive for 10 seconds"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        logger.info(f"⏱️ Starting silence monitor loop for call {call_id}")
        session_state["last_activity_time"] = time.time()
        
        try:
            while True:
                await asyncio.sleep(1.0)
                
                session_state = self.connections.get(call_id)
                if not session_state:
                    break
                    
                # Update last activity if user is speaking or bot is speaking/synthesizing
                user_is_speaking = session_state.get("user_speaking")
                
                # Safety timeout: if user_speaking has been True for more than 4.0 seconds without any words transcribed,
                # force reset it to prevent silence monitor from getting stuck due to missed SpeechEnded events or line noise.
                if user_is_speaking:
                    if "user_speaking_start_time" not in session_state:
                        session_state["user_speaking_start_time"] = time.time()
                    elif time.time() - session_state["user_speaking_start_time"] > 4.0:
                        logger.info(f"⏱️ Safety guard: Resetting stuck user_speaking state for call {call_id}")
                        session_state["user_speaking"] = False
                        user_is_speaking = False
                        if "user_speaking_start_time" in session_state:
                            try:
                                del session_state["user_speaking_start_time"]
                            except KeyError:
                                pass
                else:
                    if "user_speaking_start_time" in session_state:
                        try:
                            del session_state["user_speaking_start_time"]
                        except KeyError:
                            pass
                
                if user_is_speaking or self.is_bot_actively_speaking(call_id):
                    session_state["last_activity_time"] = time.time()
                    continue
                    
                # Check idle duration
                idle_time = time.time() - session_state.get("last_activity_time", time.time())
                if idle_time >= 10.0:
                    logger.info(f"⏱️ Silence detected for 10 seconds on call {call_id}. Injecting follow-up prompt.")
                    # Reset timer to prevent rapid repeated follow-ups
                    session_state["last_activity_time"] = time.time()
                    
                    llm_queue = session_state.get("llm_queue")
                    if llm_queue:
                        # Feed a system directive into the LLM processor queue
                        await llm_queue.put("System: The customer has been silent for 10 seconds. Please prompt them to see if they are still there or need help.")
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in silence monitor loop: {e}")

    async def cleanup_connections(self, call_id: str):
        """Closes deepgram socket and cancels tasks for a call session"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        logger.info(f"🧹 CLEANING UP modular connections for call: {call_id}")
        
        # Cancel tasks
        for task in session_state["tasks"]:
            if not task.done():
                task.cancel()
                
        # Close Deepgram WebSocket
        dg_ws = session_state.get("deepgram_ws")
        if dg_ws and dg_ws.state == State.OPEN:
            try:
                await dg_ws.close()
            except Exception as e:
                logger.debug(f"Error closing Deepgram WebSocket: {e}")
                
        # Close Sarvam WebSocket
        sarvam_ws = session_state.get("sarvam_ws")
        if sarvam_ws and hasattr(sarvam_ws, "_websocket") and sarvam_ws._websocket.open:
            try:
                await sarvam_ws._websocket.close()
            except Exception as e:
                logger.debug(f"Error closing Sarvam WebSocket: {e}")
                    
        # Remove connection
        if call_id in self.connections:
            del self.connections[call_id]
            
        logger.info(f"🧹 Cleanup complete for call: {call_id}")

    async def delayed_hangup(self, call_id: str, delay_seconds: float = 3.0):
        """Clean up and disconnect the SIP call after final speech has finished playing"""
        logger.info(f"⏳ Dynamic hangup requested for call {call_id}")
        
        try:
            session_state = self.connections.get(call_id)
            if session_state:
                # 1. Wait for LLM queue to be empty and LLM task to finish
                while True:
                    llm_q_empty = session_state.get("llm_queue") is None or session_state["llm_queue"].empty()
                    llm_task_done = session_state.get("current_llm_task") is None or session_state["current_llm_task"].done()
                    if llm_q_empty and llm_task_done:
                        break
                    logger.info(f"⏳ Waiting for LLM processing to complete for call {call_id}...")
                    await asyncio.sleep(0.3)
                    
                # 2. Wait for TTS queue to be empty and TTS task to finish
                while True:
                    tts_q_empty = session_state.get("tts_queue") is None or session_state["tts_queue"].empty()
                    tts_task_done = session_state.get("current_tts_task") is None or session_state["current_tts_task"].done()
                    if tts_q_empty and tts_task_done:
                        break
                    logger.info(f"⏳ Waiting for TTS synthesis to complete for call {call_id}...")
                    await asyncio.sleep(0.3)
                    
            # 3. Wait for PJSIP playback buffer to be empty
            if self.sip_server:
                call_state = self.sip_server.sip_calls.get(call_id)
                if call_state:
                    while hasattr(call_state, "playback_buffer") and len(call_state.playback_buffer) > 0:
                        logger.info(f"⏳ Waiting for PJSIP playback buffer ({len(call_state.playback_buffer)} bytes remaining) for call {call_id}...")
                        await asyncio.sleep(0.3)
                        
        except Exception as e:
            logger.error(f"❌ Error in dynamic hangup check: {e}")
            
        # 4. Add a short buffer (e.g. 1.5 seconds) to ensure the final speech packets are fully transmitted over RTP
        await asyncio.sleep(1.5)
        
        logger.info(f"📞 Hanging up call {call_id} now that final speech playback is complete.")
        if self.sip_server:
            await self.sip_server.cleanup_call(call_id)
