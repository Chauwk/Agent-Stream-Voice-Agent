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
        
        try:
            logger.info("⏳ Pre-generating and caching startup greeting audio...")
            response = self.sync_sarvam_client.text_to_speech.convert(
                text=self.cached_greeting_text,
                target_language_code=Config.SARVAM_LANGUAGE_CODE,
                speaker=Config.SARVAM_SPEAKER,
                model=Config.SARVAM_MODEL,
                output_audio_codec="linear16",
                speech_sample_rate=16000
            )
            if response and response.audios:
                base64_audio = response.audios[0]
                self.cached_greeting_audio = base64.b64decode(base64_audio)
                logger.info("✅ Startup greeting audio cached successfully!")
            else:
                logger.error("❌ Failed to cache greeting: Empty response from Sarvam")
        except Exception as e:
            logger.error(f"❌ Failed to pre-generate greeting: {e}")
            
        logger.info("🤖 Modular Voice Bot Engine Initialized")
        logger.info(f"   🎙️ STT Model (Deepgram): {Config.DEEPGRAM_MODEL}")
        logger.info(f"   🧠 LLM Model (Gemini): {Config.GEMINI_MODEL}")
        logger.info(f"   🔊 TTS Model (Sarvam): {Config.SARVAM_MODEL}")
        logger.info(f"   🎭 Speaker (Sarvam): {Config.SARVAM_SPEAKER}")
        logger.info(f"   🌐 Language (Sarvam): {Config.SARVAM_LANGUAGE_CODE}")

    async def start_server(self):
        """Start SIP server for direct Exotel SIP trunking"""
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

    async def connect_to_openai_enhanced(self, call_id: str):
        """
        Setup modular connection endpoints (Deepgram, Gemini, Sarvam) for the call session.
        Method name matches the SIP server interface call for backward compatibility.
        """
        logger.info(f"🔗 INITIALIZING MODULAR PIPELINE for call: {call_id}")
        
        # 1. Initialize Gemini chat model
        try:
            import os
            import json
            gcp_key = os.getenv('GCP_SERVICE_ACCOUNT_KEY') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            
            # Autodetect in root directory if not specified in env
            if not gcp_key:
                for f in os.listdir('.'):
                    if f.endswith('.json') and f.startswith('project-'):
                        gcp_key = f
                        break
                        
            if gcp_key and os.path.exists(gcp_key):
                logger.info(f"🔑 Configuring Gemini with GCP Service Account (Vertex AI asia-south1): {gcp_key}")
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(
                    gcp_key,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                with open(gcp_key, 'r') as f:
                    key_data = json.load(f)
                project_id = key_data.get('project_id')
                
                client = genai.Client(
                    vertexai=True,
                    project=project_id,
                    location="asia-south1",
                    credentials=creds
                )
            else:
                logger.info("🔑 Configuring Gemini with API Key (AI Studio)")
                client = genai.Client(api_key=Config.GEMINI_API_KEY)
                
            # Define the end_call tool closure
            async def end_call() -> str:
                """Hang up the call when the conversation is finished, the customer says goodbye, or they want to end the call."""
                logger.info(f"📞 Tool end_call invoked for call: {call_id}")
                asyncio.create_task(self.delayed_hangup(call_id))
                return "Call hangup initiated"

            system_instruction = (
                f"You are {Config.SALES_BOT_NAME}, a friendly and professional voice sales representative for {Config.COMPANY_NAME}. "
                "Your goal is to assist the caller warmly and concisely. Speak naturally, keep answers brief "
                "(1-2 sentences max) as this is a real-time phone call. Do not use markdown like bold or bullet points. "
                "When the conversation is finished or the user says goodbye, call the end_call tool to disconnect the call."
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
            
            chat_session = client.aio.chats.create(
                model=Config.GEMINI_MODEL,
                history=history,
                config={
                    "system_instruction": system_instruction,
                    "tools": [end_call]
                }
            )
        except Exception as e:
            logger.error(f"❌ Failed to configure Gemini: {e}")
            raise
            
        # 2. Establish session state structure
        self.connections[call_id] = {
            "chat_session": chat_session,
            "deepgram_ws": None,
            "tasks": [],
            "user_speaking": False,
            "is_bot_speaking": False,
            "current_context_id": None,
            "llm_queue": asyncio.Queue(),  # Queue to pass text prompts to LLM
            "tts_queue": asyncio.Queue()   # Queue to pass text chunks to TTS
        }
        
        # 3. Connect to WebSockets
        try:
            await self._connect_websockets(call_id)
            logger.info(f"✅ Deepgram WebSocket connected for call: {call_id}")
            
            session_state = self.connections[call_id]
            
            # Start background async pipeline workers
            dg_task = asyncio.create_task(self._handle_deepgram_responses(call_id))
            tts_process_task = asyncio.create_task(self._process_tts_queue(call_id))
            llm_process_task = asyncio.create_task(self._process_llm_queue(call_id))
            dg_keepalive_task = asyncio.create_task(self._send_deepgram_keepalives(call_id))
            
            session_state["tasks"].extend([dg_task, tts_process_task, llm_process_task, dg_keepalive_task])
            
            # Trigger initial greeting instantly from cache
            if self.cached_greeting_audio:
                logger.info(f"🗣️ Playing cached greeting for call: {call_id}")
                if self.sip_server:
                    await self.sip_server.send_audio_to_rtp(call_id, self.cached_greeting_audio)
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize modular pipeline sockets: {e}")
            await self.cleanup_connections(call_id)
            raise

    async def _connect_websockets(self, call_id: str):
        """Connect to Deepgram WebSocket"""
        session_state = self.connections[call_id]
        
        # Deepgram Live WS config
        dg_url = f"wss://api.deepgram.com/v1/listen?model={Config.DEEPGRAM_MODEL}&encoding=linear16&sample_rate=16000&channels=1&endpointing=300&interim_results=false"
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
                
                # Check for speech detection to handle quick interruptions
                is_final = data.get("is_final", False)
                speech_started = data.get("speech_started", False)
                
                if speech_started and not session_state["user_speaking"]:
                    session_state["user_speaking"] = True
                    logger.info(f"🎤 CUSTOMER STARTED SPEAKING for call {call_id}")
                    await self._handle_customer_interruption(call_id)
                
                channel = data.get("channel", {})
                alternatives = channel.get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")
                    if transcript.strip() and is_final:
                        logger.info(f"🎤 CUSTOMER SAID: {transcript}")
                        session_state["user_speaking"] = False
                        
                        # Forward transcription text to the LLM processor queue
                        await session_state["llm_queue"].put(transcript)
                        
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"🔌 Deepgram connection closed for call {call_id}: code={e.code}, reason='{e.reason}'")
        except Exception as e:
            logger.error(f"❌ Error handling Deepgram messages for call {call_id}: {e}")

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
        """Listens for user transcripts, queries Gemini 1.5, and pushes sentence blocks to the TTS queue"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        chat_session = session_state["chat_session"]
        llm_queue = session_state["llm_queue"]
        tts_queue = session_state["tts_queue"]
        
        try:
            while True:
                prompt = await llm_queue.get()
                logger.info(f"🧠 Querying Gemini LLM with: '{prompt}'")
                
                session_state["is_bot_speaking"] = True
                # Set a unique context ID for this speech turn
                context_id = f"ctx_{int(time.time() * 1000)}"
                session_state["current_context_id"] = context_id
                
                try:
                    # Async stream Gemini response
                    response = await chat_session.send_message_stream(prompt)
                    current_sentence = ""
                    
                    async for chunk in response:
                        # If user started speaking during generation, break immediately
                        if session_state["user_speaking"]:
                            logger.info("🧠 Gemini generation interrupted by customer.")
                            break
                        
                        text_delta = chunk.text
                        if text_delta:
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
                                        # Skip this boundary and look for the next punctuation
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
                                            # No further punctuation in current buffer, wait for more stream tokens
                                            break
                                            
                                sentence_to_send = current_sentence[:idx+1].strip()
                                current_sentence = current_sentence[idx+1:]
                                
                                if sentence_to_send:
                                    await tts_queue.put((context_id, sentence_to_send))
                                    
                    # Send any remaining text
                    if current_sentence.strip() and not session_state["user_speaking"]:
                        await tts_queue.put((context_id, current_sentence.strip()))
                    
                except Exception as e:
                    logger.error(f"❌ Gemini generation error: {e}")
                finally:
                    llm_queue.task_done()
                    
        except asyncio.CancelledError:
            pass

    async def _process_tts_queue(self, call_id: str):
        """Listens for sentences and invokes Sarvam AI TTS asynchronously"""
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
                
                logger.info(f"🔊 Requesting Sarvam TTS for sentence: '{sentence_text}'")
                
                try:
                    # Run the native async client call directly
                    response = await self.sarvam_client.text_to_speech.convert(
                        text=sentence_text,
                        target_language_code=Config.SARVAM_LANGUAGE_CODE,
                        speaker=Config.SARVAM_SPEAKER,
                        model=Config.SARVAM_MODEL,
                        output_audio_codec="linear16",
                        speech_sample_rate=16000
                    )
                    
                    # Verify again that context has not changed while API request was running
                    if context_id != session_state["current_context_id"]:
                        logger.info(f"🚫 Context changed during TTS gen. Discarding output for: '{sentence_text}'")
                        tts_queue.task_done()
                        continue
                        
                    if response and response.audios:
                        base64_audio = response.audios[0]
                        pcm_audio = base64.b64decode(base64_audio)
                        
                        logger.info(f"🗣️ SARAH SPEAKING: {sentence_text}")
                        
                        if self.sip_server:
                            await self.sip_server.send_audio_to_rtp(call_id, pcm_audio)
                    else:
                        logger.error(f"❌ Empty or invalid response from Sarvam AI for: '{sentence_text}'")
                        
                except Exception as e:
                    logger.error(f"❌ Error generating TTS from Sarvam AI: {e}")
                    
                tts_queue.task_done()
                
        except asyncio.CancelledError:
            pass

    async def _handle_customer_interruption(self, call_id: str):
        """Immediately stops bot speaking and clears PJSIP queues on customer interruption"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        logger.info(f"⚡ INTERRUPTING BOT for call {call_id}")
        
        # 1. Invalidate current context
        session_state["current_context_id"] = None
        session_state["is_bot_speaking"] = False
        
        # 2. Flush PJSIP playout buffer
        if self.sip_server:
            call_state = self.sip_server.sip_calls.get(call_id)
            if call_state:
                call_state.playback_buffer = b""
                call_state.is_playing = False
                logger.info(f"🔇 SIP playout buffer cleared for call {call_id}")
                
        # 3. Clear pending TTS queue
        while not session_state["tts_queue"].empty():
            try:
                session_state["tts_queue"].get_nowait()
                session_state["tts_queue"].task_done()
            except asyncio.QueueEmpty:
                break

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
                    
        # Remove connection
        if call_id in self.connections:
            del self.connections[call_id]
            
        logger.info(f"🧹 Cleanup complete for call: {call_id}")

    async def delayed_hangup(self, call_id: str, delay_seconds: float = 3.0):
        """Clean up and disconnect the SIP call after a short delay to let final speech frames finish playing"""
        logger.info(f"⏳ Delayed hangup initiated for call {call_id} (delay: {delay_seconds}s)")
        await asyncio.sleep(delay_seconds)
        if self.sip_server:
            await self.sip_server.cleanup_call(call_id)
