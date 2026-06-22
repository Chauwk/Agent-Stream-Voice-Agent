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
import google.generativeai as genai
from sarvamai import SarvamAI
from config import Config

logger = logging.getLogger(__name__)

class ModularSalesBot:
    """Modular Voice AI bot integrating Deepgram, Gemini, and Sarvam AI with PJSIP telephony"""
    
    def __init__(self):
        self.default_sample_rate = Config.DEFAULT_SAMPLE_RATE
        self.sip_server = None
        
        # Connections state map: call_id -> session state
        self.connections = {}
        
        # Initialize Sarvam Client
        self.sarvam_client = SarvamAI(api_subscription_key=Config.SARVAM_API_KEY)
        
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
            genai.configure(api_key=Config.GEMINI_API_KEY)
            system_instruction = (
                f"You are {Config.SALES_BOT_NAME}, a friendly and professional voice sales representative for {Config.COMPANY_NAME}. "
                "Your goal is to assist the caller warmly and concisely. Speak naturally, keep answers brief "
                "(1-2 sentences max) as this is a real-time phone call. Do not use markdown like bold or bullet points."
            )
            llm_model = genai.GenerativeModel(
                model_name=Config.GEMINI_MODEL,
                system_instruction=system_instruction
            )
            chat_session = llm_model.start_chat(history=[])
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
            
            session_state["tasks"].extend([dg_task, tts_process_task, llm_process_task])
            
            # Trigger initial greeting
            greeting_prompt = (
                "A customer just called our sales line. "
                "Please greet them warmly and ask how you can help them today."
            )
            await session_state["llm_queue"].put(greeting_prompt)
            
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
        
        dg_ws = await websockets.connect(dg_url, extra_headers=dg_headers)
        session_state["deepgram_ws"] = dg_ws

    async def send_audio_to_openai(self, call_id: str, audio_chunk: bytes, sample_rate: int = 16000):
        """
        Accepts raw PCM16 audio from the caller call and streams it to Deepgram.
        Method name matches the SIP server interface call for backward compatibility.
        """
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        dg_ws = session_state.get("deepgram_ws")
        if dg_ws and not dg_ws.closed:
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
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"🔌 Deepgram connection closed for call {call_id}")
        except Exception as e:
            logger.error(f"❌ Error handling Deepgram messages for call {call_id}: {e}")

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
                    response = await chat_session.send_message_async(prompt, stream=True)
                    current_sentence = ""
                    
                    async for chunk in response:
                        # If user started speaking during generation, break immediately
                        if session_state["user_speaking"]:
                            logger.info("🧠 Gemini generation interrupted by customer.")
                            break
                        
                        text_delta = chunk.text
                        if text_delta:
                            current_sentence += text_delta
                            
                            # Split by sentence boundaries (., ?, !, \n)
                            while True:
                                idx = -1
                                for p in ['.', '?', '!', '\n']:
                                    p_idx = current_sentence.find(p)
                                    if p_idx != -1:
                                        if idx == -1 or p_idx < idx:
                                            idx = p_idx
                                            
                                if idx == -1:
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
        """Listens for sentences and invokes Sarvam AI TTS in a thread pool executor"""
        session_state = self.connections.get(call_id)
        if not session_state:
            return
            
        tts_queue = session_state["tts_queue"]
        loop = asyncio.get_running_loop()
        
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
                    # Run the synchronous client call in a thread executor
                    response = await loop.run_in_executor(
                        None,
                        lambda: self.sarvam_client.text_to_speech.convert(
                            text=sentence_text,
                            target_language_code=Config.SARVAM_LANGUAGE_CODE,
                            speaker=Config.SARVAM_SPEAKER,
                            model=Config.SARVAM_MODEL,
                            output_audio_codec="linear16",
                            speech_sample_rate=16000
                        )
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
        if dg_ws and not dg_ws.closed:
            try:
                await dg_ws.close()
            except Exception as e:
                logger.debug(f"Error closing Deepgram WebSocket: {e}")
                    
        # Remove connection
        if call_id in self.connections:
            del self.connections[call_id]
            
        logger.info(f"🧹 Cleanup complete for call: {call_id}")
