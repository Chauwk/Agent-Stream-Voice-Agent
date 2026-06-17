#!/usr/bin/env python3
"""
OpenAI Realtime Sales Bot - SIP Trunking Only Version

Direct SIP Trunking integration with OpenAI Realtime API for natural conversations
Bridges Exotel SIP trunk communication with OpenAI for high-quality voice interactions.

Security Notice: This code uses environment variables for sensitive configuration.
Set OPENAI_API_KEY environment variable before running.
"""

import asyncio
import websockets
import json
import logging
import base64
import time
import struct
import ssl
import os
import re
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import Config

# Configure enhanced logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper()),
    format=Config.LOG_FORMAT
)
logger = logging.getLogger(__name__)

class OpenAIRealtimeSalesBot:
    def __init__(self):
        # Validate configuration first
        Config.validate()
        
        self.openai_connections: Dict[str, Any] = {}
        
        # Enhanced audio buffering with dynamic sample rate support
        self.audio_buffers: Dict[str, bytes] = {}
        self.connection_sample_rates: Dict[str, int] = {}  # Track sample rate per connection
        self.connection_chunk_sizes: Dict[str, int] = {}   # Track chunk size per connection
        
        # Default audio configuration (will be updated per connection)
        self.default_sample_rate = Config.DEFAULT_SAMPLE_RATE
        self.min_chunk_size_ms = Config.MIN_CHUNK_SIZE_MS
        self.buffer_size_ms = Config.BUFFER_SIZE_MS
        
        # OpenAI Configuration - SECURE: Load from environment variables
        self.openai_api_key = Config.OPENAI_API_KEY
        self.openai_model = Config.OPENAI_MODEL
        self.openai_voice = Config.OPENAI_VOICE
        
        # Enhanced features flags
        self.exotel_enhanced_events = Config.EXOTEL_MARK_CLEAR_ENHANCED
        self.variable_chunk_support = Config.EXOTEL_VARIABLE_CHUNK_SUPPORT
        self.dynamic_chunk_sizing = Config.DYNAMIC_CHUNK_SIZING
        
        self.sip_server = None
        
        # Register bot instance for telemetry queries
        from controllers import bot_controller
        bot_controller.active_bot_instance = self
        
        logger.info("🤖 Enhanced OpenAI Realtime Sales Bot initialized!")
        logger.info(f"🎵 Multi-sample rate support: {Config.SUPPORTED_SAMPLE_RATES} Hz")
        logger.info(f"📦 Variable chunk sizes: {self.min_chunk_size_ms}ms - {Config.MAX_CHUNK_SIZE_MS}ms")
        logger.info(f"✨ Enhanced Exotel events: {self.exotel_enhanced_events}")
        logger.info(f"🏢 Company: {Config.COMPANY_NAME}")
        logger.info(f"👤 Sales Rep: {Config.SALES_REP_NAME}")
        logger.info("📡 MODE: Direct SIP Trunking (cost-effective, no applet needed)")

    async def connect_to_openai_enhanced(self, stream_id: str):
        """Establish enhanced connection to OpenAI Realtime API with dynamic configuration"""
        try:
            sample_rate = self.connection_sample_rates.get(stream_id, self.default_sample_rate)
            logger.info(f"🔗 CONNECTING TO OPENAI (ENHANCED) for {stream_id} @ {sample_rate}Hz")
            
            # Enhanced URL for latest OpenAI Realtime API
            url = f"wss://api.openai.com/v1/realtime?model={self.openai_model}"
            
            # Create SSL context that handles certificate verification
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Enhanced headers for latest API version
            headers = [
                ("Authorization", f"Bearer {self.openai_api_key}")
            ]
            
            # Determine correct header parameter based on websockets library version
            import inspect
            connect_params = inspect.signature(websockets.connect).parameters
            connect_kwargs = {
                "ssl": ssl_context,
                "ping_interval": 20,
                "ping_timeout": 10
            }
            if "additional_headers" in connect_params:
                connect_kwargs["additional_headers"] = dict(headers)
            else:
                connect_kwargs["extra_headers"] = dict(headers)
                
            openai_ws = await websockets.connect(url, **connect_kwargs)
            
            # Get enhanced session configuration
            session_config = Config.get_enhanced_session_config(sample_rate, self.openai_voice)
            
            input_format = session_config['audio']['input']['format']['type']
            output_format = session_config['audio']['output']['format']['type']
            
            self.openai_connections[stream_id] = {
                "websocket": openai_ws,
                "start_time": time.time(),
                "sample_rate": sample_rate,
                "input_format": input_format,
                "output_format": output_format,
                "session_config": session_config,
                "user_speaking": False
            }
            
            logger.info(f"✅ ENHANCED OPENAI CONNECTED for {stream_id} @ {sample_rate}Hz")
            logger.info(f"🎵 Audio Format: {input_format} → {output_format}")
            
            # Configure enhanced OpenAI session
            await self.configure_openai_session_enhanced(stream_id)
            
            # Start listening to OpenAI responses
            asyncio.create_task(self.handle_openai_responses_enhanced(stream_id, openai_ws))
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to OpenAI (enhanced): {e}")
            logger.error(f"Error type: {type(e).__name__}")
            if "SSL" in str(e):
                logger.error("💡 SSL Error - trying with insecure SSL context")
            elif "authentication" in str(e).lower():
                logger.error("💡 Authentication Error - check OpenAI API key")
            elif "websocket" in str(e).lower():
                logger.error("💡 WebSocket Error - check connection and headers")

    async def configure_openai_session_enhanced(self, stream_id: str):
        """Configure enhanced OpenAI Realtime session"""
        try:
            openai_connection = self.openai_connections[stream_id]
            openai_ws = openai_connection["websocket"]
            session_config = openai_connection["session_config"]
            sample_rate = openai_connection["sample_rate"]
            
            # Send enhanced session configuration
            session_update = {
                "type": "session.update",
                "session": session_config
            }
            
            await openai_ws.send(json.dumps(session_update))
            
            input_format = session_config['audio']['input']['format']['type']
            output_format = session_config['audio']['output']['format']['type']
            voice = session_config['audio']['output']['voice']
            
            logger.info(f"🔧 ENHANCED OPENAI SESSION CONFIGURED for {stream_id}")
            logger.info(f"   🎵 Sample Rate: {sample_rate}Hz")
            logger.info(f"   🎤 Input Format: {input_format}")
            logger.info(f"   🔊 Output Format: {output_format}")
            logger.info(f"   🎭 Voice: {voice}")
            
            # Send enhanced initial greeting
            await self.send_initial_greeting_enhanced(stream_id)
            
        except Exception as e:
            logger.error(f"❌ Error configuring enhanced OpenAI session: {e}")

    async def send_initial_greeting_enhanced(self, stream_id: str):
        """Send enhanced initial sales greeting through OpenAI"""
        try:
            openai_ws = self.openai_connections[stream_id]["websocket"]
            sample_rate = self.connection_sample_rates.get(stream_id, self.default_sample_rate)
            
            # Create enhanced conversation item with greeting
            greeting_msg = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_text", 
                        "text": f"A customer just called our sales line. The connection is running at {sample_rate}Hz audio quality. Please greet them warmly and ask how you can help them today."
                    }]
                }
            }
            
            await openai_ws.send(json.dumps(greeting_msg))
            
            # Create enhanced response with audio focus
            response_msg = {
                "type": "response.create",
                "response": {
                    "output_modalities": ["audio"],
                    "instructions": "Give a warm, professional greeting. Keep it concise and natural."
                }
            }
            await openai_ws.send(json.dumps(response_msg))
            
            logger.info(f"👋 ENHANCED INITIAL GREETING SENT for {stream_id} @ {sample_rate}Hz")
            
        except Exception as e:
            logger.error(f"❌ Error sending enhanced initial greeting: {e}")

    async def handle_openai_responses_enhanced(self, stream_id: str, openai_ws):
        """Handle enhanced responses from OpenAI Realtime API"""
        try:
            async for message in openai_ws:
                try:
                    data = json.loads(message)
                    event_type = data.get("type", "")
                    
                    logger.debug(f"🤖 ENHANCED OPENAI EVENT: {event_type} for {stream_id}")
                    
                    if event_type == "response.output_audio.delta":
                        openai_config = self.openai_connections.get(stream_id)
                        if openai_config and not openai_config.get("user_speaking", False):
                            await self.handle_openai_audio_delta_enhanced(stream_id, data)
                    elif event_type == "response.function_call_arguments.done":
                        await self.handle_openai_function_call_enhanced(stream_id, data)
                    elif event_type == "response.output_audio_transcript.delta":
                        transcript_delta = data.get('delta', '')
                        if transcript_delta.strip():
                            logger.info(f"🗣️ SARAH SPEAKING: {transcript_delta}")
                    elif event_type == "input_audio_buffer.speech_started":
                        logger.info(f"🎤 CUSTOMER STARTED SPEAKING (enhanced) for {stream_id}")
                        openai_config = self.openai_connections.get(stream_id)
                        if openai_config:
                            openai_config["user_speaking"] = True
                        # Enhanced interruption handling
                        await self._handle_customer_interruption(stream_id, openai_ws)
                    elif event_type == "input_audio_buffer.speech_stopped":
                        logger.info(f"🎤 CUSTOMER STOPPED SPEAKING (enhanced) for {stream_id}")
                        openai_config = self.openai_connections.get(stream_id)
                        if openai_config:
                            openai_config["user_speaking"] = False
                        # Enhanced response generation
                        await self.trigger_openai_response_enhanced(stream_id, openai_ws)
                    elif event_type == "response.done":
                        logger.info(f"✅ SARAH FINISHED RESPONSE (enhanced) for {stream_id}")
                    elif event_type == "error":
                        logger.error(f"❌ ENHANCED OPENAI ERROR: {data}")
                    elif event_type == "session.updated":
                        logger.info(f"🔧 SESSION UPDATED for {stream_id}")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON decode error from OpenAI (enhanced): {e}")
                except Exception as e:
                    logger.error(f"❌ Error processing enhanced OpenAI response: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Error in enhanced OpenAI response handler: {e}")

    async def _handle_customer_interruption(self, stream_id: str, openai_ws):
        """Handle customer interruption with enhanced response cancellation"""
        try:
            # Enhanced interruption handling
            cancel_response_msg = {
                "type": "response.cancel"
            }
            await openai_ws.send(json.dumps(cancel_response_msg))
            logger.info(f"🛑 ENHANCED BOT INTERRUPTED - Customer started speaking for {stream_id}")
            
            # IMMEDIATELY clear the playback buffer in SIP Server so the bot stops speaking instantly
            if self.sip_server and stream_id in self.sip_server.sip_calls:
                call_state = self.sip_server.sip_calls[stream_id]
                call_state.playback_buffer = b""
                call_state.is_playing = False
                logger.info(f"🔇 Cleared playback buffer for {stream_id} due to interruption")
            
        except Exception as e:
            logger.error(f"❌ Error handling enhanced customer interruption: {e}")

    async def trigger_openai_response_enhanced(self, stream_id: str, openai_ws):
        """Trigger enhanced OpenAI response generation with improved parameters"""
        try:
            # Enhanced response triggering with better configuration
            await asyncio.sleep(0.2)  # Optimized pause verification
            
            response_create = {
                "type": "response.create",
                "response": {
                    "output_modalities": ["audio"],
                    "instructions": "Respond naturally and conversationally. Use appropriate pauses and inflections."
                }
            }
            await openai_ws.send(json.dumps(response_create))
            logger.info(f"🎯 TRIGGERED ENHANCED OPENAI RESPONSE for {stream_id}")
            
        except Exception as e:
            logger.error(f"❌ Error triggering enhanced OpenAI response: {e}")

    async def handle_openai_function_call_enhanced(self, stream_id: str, data: dict):
        """Handle enhanced function calls from OpenAI with improved error handling"""
        try:
            function_name = data.get("name", "")
            arguments = json.loads(data.get("arguments", "{}"))
            call_id = data.get("call_id", "")
            
            logger.info(f"🔧 ENHANCED FUNCTION CALL: {function_name} with {arguments}")
            
            # Execute function with enhanced error handling
            if function_name == "schedule_demo":
                result = await self.schedule_demo_enhanced(arguments)
            elif function_name == "send_pricing_info":
                result = await self.send_pricing_info_enhanced(arguments)
            elif function_name == "transfer_to_human":
                result = await self.transfer_to_human_enhanced(stream_id, arguments)
            else:
                result = {"status": "unknown_function", "error": f"Function {function_name} not implemented"}
            
            # Send enhanced function result back to OpenAI
            openai_ws = self.openai_connections[stream_id]["websocket"]
            
            function_response = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result)
                }
            }
            
            await openai_ws.send(json.dumps(function_response))
            
            # Create enhanced response
            response_msg = {
                "type": "response.create",
                "response": {
                    "output_modalities": ["audio"],
                    "instructions": f"Based on the function result, provide a natural response to the customer about {function_name}."
                }
            }
            await openai_ws.send(json.dumps(response_msg))
            
            logger.info(f"✅ ENHANCED FUNCTION CALL COMPLETED: {function_name}")
            
        except Exception as e:
            logger.error(f"❌ Error handling enhanced function call: {e}")

    async def schedule_demo_enhanced(self, args: dict) -> dict:
        """Enhanced demo scheduling with better data capture"""
        logger.info(f"📅 SCHEDULING ENHANCED DEMO: {args}")
        
        # Extract enhanced information
        customer_name = args.get('customer_name', 'Customer')
        product_interest = args.get('product_interest', 'Our solutions')
        company = args.get('company', '')
        contact_info = {
            'email': args.get('contact_email', ''),
            'phone': args.get('contact_phone', '')
        }
        preferences = {
            'date': args.get('preferred_date', ''),
            'time': args.get('preferred_time', ''),
            'notes': args.get('additional_notes', '')
        }
        
        # In production, this would integrate with CRM/scheduling system
        return {
            "status": "success",
            "message": f"Demo scheduled for {customer_name} interested in {product_interest}",
            "demo_id": f"DEMO_{int(time.time())}",
            "customer_name": customer_name,
            "product_interest": product_interest,
            "company": company,
            "contact_info": contact_info,
            "preferences": preferences,
            "scheduled_at": time.strftime('%Y-%m-%d %H:%M:%S')
        }

    async def send_pricing_info_enhanced(self, args: dict) -> dict:
        """Enhanced pricing information with detailed breakdown"""
        logger.info(f"💰 SENDING ENHANCED PRICING INFO: {args}")
        
        product = args.get('product', 'Our solution')
        company_size = args.get('company_size', 'standard')
        contact_email = args.get('contact_email', '')
        custom_requirements = args.get('custom_requirements', '')
        
        # In production, this would calculate custom pricing
        return {
            "status": "success", 
            "message": f"Detailed pricing information for {product} will be sent to {contact_email}",
            "product": product,
            "company_size": company_size,
            "contact_email": contact_email,
            "custom_requirements": custom_requirements,
            "quote_id": f"QUOTE_{int(time.time())}",
            "estimated_delivery": "within 24 hours"
        }

    async def transfer_to_human_enhanced(self, stream_id: str, args: dict) -> dict:
        """Enhanced human transfer with context preservation"""
        logger.info(f"👥 TRANSFERRING TO HUMAN AGENT: {args}")
        
        reason = args.get('reason', 'Customer request')
        context = args.get('customer_context', 'No additional context')
        urgency = args.get('urgency', 'medium')
        
        # In production, this would interface with call center system
        transfer_result = {
            "status": "transfer_initiated",
            "message": f"Transferring to human agent - {reason}",
            "transfer_id": f"TRANSFER_{int(time.time())}",
            "reason": reason,
            "context": context,
            "urgency": urgency,
            "stream_id": stream_id,
            "estimated_wait": "2-3 minutes"
        }
        
        # Log for human agent context
        logger.info(f"🚨 HUMAN TRANSFER INITIATED for {stream_id}:")
        logger.info(f"   Reason: {reason}")
        logger.info(f"   Context: {context}")
        logger.info(f"   Urgency: {urgency}")
        
        return transfer_result

    def _resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Resample audio between different sample rates"""
        if from_rate == to_rate:
            return audio_data
            
        try:
            # Use the media resampler for high-quality resampling
            if not hasattr(self, 'resampler') or self.resampler is None:
                from engines.media_resampler import MediaResampler
                self.resampler = MediaResampler()
            
            resampled = self.resampler.resample_audio(
                audio_data=audio_data,
                from_rate=from_rate,
                to_rate=to_rate,
                channels=1,
                sample_width=2
            )
            
            if resampled:
                logger.debug(f"🔄 RESAMPLED AUDIO: {from_rate}Hz → {to_rate}Hz")
                return resampled
            else:
                logger.warning(f"⚠️ RESAMPLING FAILED, using original audio")
                return audio_data
                
        except Exception as e:
            logger.error(f"❌ Error resampling audio: {e}")
            return audio_data

    def apply_noise_suppression(self, audio_data: bytes, sample_rate: int) -> bytes:
        """Enhanced noise suppression with sample rate awareness"""
        if not Config.AUDIO_ENHANCEMENT_ENABLED:
            return audio_data
            
        try:
            import numpy as np
            
            # Convert to 16-bit signed integers
            audio_samples = np.frombuffer(audio_data, dtype=np.int16)
            
            # Enhanced noise gate with sample rate adjustment
            noise_threshold = Config.NOISE_THRESHOLD * (sample_rate / 8000)  # Scale with sample rate
            audio_samples = np.where(np.abs(audio_samples) < noise_threshold, 0, audio_samples)
            
            # Sample rate specific filtering
            if len(audio_samples) > 10:
                # Adjust filter parameters based on sample rate
                if sample_rate >= 24000:
                    window_size = min(7, len(audio_samples) // 2)  # Larger window for higher sample rates
                elif sample_rate >= 16000:
                    window_size = min(5, len(audio_samples) // 2)
                else:
                    window_size = min(3, len(audio_samples) // 2)
                
                # Enhanced high-pass filter
                moving_avg = np.convolve(audio_samples.astype(np.float32), 
                                       np.ones(window_size)/window_size, mode='same')
                audio_samples = audio_samples - moving_avg.astype(np.int16) * 0.15
            
            # Enhanced dynamic range compression
            max_val = np.max(np.abs(audio_samples))
            if max_val > 0:
                # Adaptive compression based on sample rate
                compression_ratio = 0.85 if sample_rate >= 16000 else 0.8
                normalized = audio_samples.astype(np.float32) / max_val
                compressed = np.sign(normalized) * (np.abs(normalized) ** compression_ratio)
                audio_samples = (compressed * max_val * 0.9).astype(np.int16)
            
            return audio_samples.tobytes()
            
        except ImportError:
            logger.warning("📢 NumPy not available - skipping enhanced noise suppression")
            return audio_data
        except Exception as e:
            logger.error(f"❌ Error in enhanced noise suppression: {e}")
            return audio_data

    def generate_test_tone(self, duration_ms: int = 200, frequency: int = 800, sample_rate: int = None) -> bytes:
        """Generate enhanced test tone with configurable sample rate"""
        import math
        
        if sample_rate is None:
            sample_rate = self.default_sample_rate
            
        samples = int(sample_rate * duration_ms / 1000)
        amplitude = 5000  # Moderate volume
        
        audio_data = []
        for i in range(samples):
            # Generate sine wave
            t = i / sample_rate
            sample = int(amplitude * math.sin(2 * math.pi * frequency * t))
            sample = max(-32767, min(32767, sample))  # Clamp to 16-bit range
            audio_data.append(sample)
        
        # Convert to 16-bit PCM bytes (little-endian)
        return struct.pack(f'<{len(audio_data)}h', *audio_data)

    def convert_pcm_to_ulaw(self, pcm_data: bytes) -> bytes:
        """Convert 16-bit PCM to G.711 u-law (same sample rate)"""
        try:
            import audioop
            return audioop.lin2ulaw(pcm_data, 2)
        except ImportError:
            # G.711 u-law encoding table (simplified fallback)
            samples_pcm = struct.unpack(f'<{len(pcm_data)//2}h', pcm_data)
            ulaw_bytes = []
            
            for sample in samples_pcm:
                # Clamp to 14-bit range
                sample = max(-8159, min(8159, sample))
                
                # Sign and magnitude
                if sample < 0:
                    sample = -sample
                    sign = 0x80
                else:
                    sign = 0x00
                
                # Find the segment
                if sample < 32:
                    segment = 0
                    quantized = sample >> 1
                elif sample < 96:
                    segment = 1
                    quantized = (sample - 32) >> 2
                elif sample < 224:
                    segment = 2
                    quantized = (sample - 96) >> 3
                elif sample < 480:
                    segment = 3
                    quantized = (sample - 224) >> 4
                elif sample < 992:
                    segment = 4
                    quantized = (sample - 480) >> 5
                elif sample < 2016:
                    segment = 5
                    quantized = (sample - 992) >> 6
                elif sample < 4064:
                    segment = 6
                    quantized = (sample - 2016) >> 7
                else:
                    segment = 7
                    quantized = (sample - 4064) >> 8
                
                # Combine sign, segment, and quantized value
                ulaw_value = sign | (segment << 4) | quantized
                ulaw_bytes.append(ulaw_value ^ 0xFF)  # Complement for u-law
            
            return bytes(ulaw_bytes)

    def convert_ulaw_to_pcm(self, ulaw_data: bytes) -> bytes:
        """Convert G.711 u-law to 16-bit PCM (same sample rate)"""
        try:
            import audioop
            return audioop.ulaw2lin(ulaw_data, 2)
        except ImportError:
            # G.711 u-law decoding table (simplified fallback)
            pcm_samples = []
            
            for ulaw_byte in ulaw_data:
                ulaw_byte ^= 0xFF  # Un-complement
                
                sign = ulaw_byte & 0x80
                segment = (ulaw_byte >> 4) & 0x07
                quantized = ulaw_byte & 0x0F
                
                # Decode based on segment
                if segment == 0:
                    pcm_val = (quantized << 1) + 1
                elif segment == 1:
                    pcm_val = ((quantized << 2) + 33)
                elif segment == 2:
                    pcm_val = ((quantized << 3) + 97)
                elif segment == 3:
                    pcm_val = ((quantized << 4) + 225)
                elif segment == 4:
                    pcm_val = ((quantized << 5) + 481)
                elif segment == 5:
                    pcm_val = ((quantized << 6) + 993)
                elif segment == 6:
                    pcm_val = ((quantized << 7) + 2017)
                else:  # segment == 7
                    pcm_val = ((quantized << 8) + 4065)
                
                # Apply sign
                if sign:
                    pcm_val = -pcm_val
                
                # Scale up to 16-bit range from 14-bit range (multiply by 4)
                pcm_val = pcm_val << 2
                
                pcm_samples.append(pcm_val)
            
            return struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)


    async def start_server(self):
        """Start SIP server for direct Exotel SIP trunking"""
        try:
            logger.info(f'🚀 Starting SIP Server on {Config.SIP_SERVER_HOST}:{Config.SIP_SERVER_PORT}')
            logger.info('📞 Ready for direct Exotel SIP trunk connections!')
            logger.info('💰 Cost-effective mode: No Voicebot Applet needed')
            logger.info('🎵 Multi-sample rate support: 8kHz, 16kHz, 24kHz')
            logger.info('🔐 Using SIP authentication from environment')
            
            # Import SIP server
            from core.sip_server import SIPServer
            
            # Create and start SIP server
            self.sip_server = SIPServer(openai_bot=self)
            
            # Initialize PJSUA (may take a moment)
            logger.info("⏳ Initializing PJSUA2 SIP stack...")
            self.sip_server.initialize_pjsua()
            
            # Start SIP server
            await self.sip_server.start()
            
            logger.info(f'✅ SIP Server running at sip://{Config.SIP_SERVER_HOST}:{Config.SIP_SERVER_PORT}')
            logger.info(f'📤 Outbound calls: Use ExotelOutboundAPI (REST API)')
            logger.info('📞 Waiting for incoming SIP calls...')
            
            # Keep running
            await asyncio.Future()  # Run forever
            
        except ImportError as e:
            logger.error(f'❌ SIP libraries not installed: {e}')
            logger.error('💡 Install with: pip install pjsua2-py PyAudio')
            raise
        except Exception as e:
            logger.error(f'❌ SIP Server Error: {e}')
            raise
        finally:
            if self.sip_server:
                await self.sip_server.stop()

    async def handle_exotel_dtmf(self, message: Dict[str, Any], stream_id: str):
        """Handle DTMF events from Exotel"""
        try:
            dtmf_data = message.get('dtmf', {})
            digit = dtmf_data.get('digit', '')
            duration = dtmf_data.get('duration', '')
            
            logger.info(f'📞 DTMF received: {digit} (duration: {duration}ms) for {stream_id}')
            
            # Handle DTMF logic here
            # For now, just acknowledge
            
        except Exception as e:
            logger.error(f'❌ Error handling DTMF: {e}')
    
    async def send_audio_to_openai(self, call_id: str, audio_chunk: bytes, sample_rate: int = 16000):
        """
        Public method for SIP server to send RTP audio to OpenAI
        This bridges incoming RTP audio packets with OpenAI Realtime API
        
        Args:
            call_id: SIP call identifier
            audio_chunk: PCM16 audio data
            sample_rate: Audio sample rate (8000, 16000, 24000)
        """
        try:
            # Map call_id to stream_id for compatibility with existing methods
            stream_id = call_id
            
            # Ensure OpenAI connection exists
            if stream_id not in self.openai_connections:
                logger.warning(f"⚠️ No OpenAI connection for SIP call {call_id}")
                return
            
            # Initialize sample rate tracking if needed
            if stream_id not in self.connection_sample_rates:
                self.connection_sample_rates[stream_id] = sample_rate
            
            # Send audio to OpenAI via existing method
            await self._send_audio_to_openai(stream_id, audio_chunk, sample_rate)
            
        except Exception as e:
            logger.error(f"❌ Error sending RTP audio to OpenAI for {call_id}: {e}")

    async def _send_audio_to_openai(self, stream_id: str, chunk: bytes, sample_rate: int):
        """Send audio chunk to OpenAI with proper format and sample rate handling"""
        try:
            openai_config = self.openai_connections[stream_id]
            input_format = openai_config.get("input_format", "g711_ulaw")
            
            # Initialize buffer if not exists
            if stream_id not in self.audio_buffers:
                self.audio_buffers[stream_id] = b""
                
            # Append new chunk to buffer
            self.audio_buffers[stream_id] += chunk
            
            # Calculate buffer threshold (e.g. 160ms)
            buffer_ms = self.buffer_size_ms
            bytes_needed = int(sample_rate * 2 * buffer_ms / 1000)
            
            if len(self.audio_buffers[stream_id]) < bytes_needed:
                return  # Keep buffering
                
            # Extract buffered audio to process
            processed_audio = self.audio_buffers[stream_id]
            self.audio_buffers[stream_id] = b""  # Reset buffer
            
            # Apply noise suppression if enabled
            if Config.AUDIO_ENHANCEMENT_ENABLED:
                processed_audio = self.apply_noise_suppression(processed_audio, sample_rate)
            
            if input_format in ["g711_ulaw", "audio/pcmu"]:
                # Exotel/OpenAI expects 8kHz u-law.
                # If incoming is 16kHz PCM16, resample to 8kHz PCM16 first.
                if sample_rate != 8000:
                    processed_audio = self._resample_audio(processed_audio, sample_rate, 8000)
                # Convert 8kHz PCM16 to 8kHz u-law
                openai_audio = self.convert_pcm_to_ulaw(processed_audio)
            elif input_format == "pcm16":
                # OpenAI expects 24kHz PCM16.
                # If incoming is 16kHz, resample 16kHz PCM16 -> 24kHz PCM16.
                if sample_rate != 24000:
                    openai_audio = self._resample_audio(processed_audio, sample_rate, 24000)
                else:
                    openai_audio = processed_audio
            else:
                # Fallback
                openai_audio = processed_audio
                
            openai_audio_b64 = base64.b64encode(openai_audio).decode()
            
            # Send to OpenAI Realtime API
            openai_msg = {
                "type": "input_audio_buffer.append",
                "audio": openai_audio_b64
            }
            
            openai_ws = openai_config["websocket"]
            await openai_ws.send(json.dumps(openai_msg))
            
            logger.debug(f"📤 AUDIO SENT TO OPENAI: {len(openai_audio)} bytes {input_format} (from {len(processed_audio)} bytes PCM @ {sample_rate}Hz)")
            
        except Exception as e:
            logger.error(f"❌ Error sending audio to OpenAI: {e}")

    async def handle_openai_audio_delta_enhanced(self, stream_id: str, data: dict):
        """Handle audio response from OpenAI and send to SIP server for playback"""
        try:
            if not self.sip_server:
                logger.warning(f"⚠️ SIP Server not initialized, cannot play OpenAI audio delta")
                return
                
            # Get audio from OpenAI (base64 encoded)
            audio_delta = data.get("delta", "")
            if not audio_delta:
                return
            
            # Get connection settings
            openai_config = self.openai_connections[stream_id]
            output_format = openai_config.get("output_format", "g711_ulaw")
            
            # Decode audio
            openai_audio = base64.b64decode(audio_delta)
            
            # Convert to 16kHz PCM16 Mono expected by PJSUA2
            if output_format in ["g711_ulaw", "audio/pcmu"]:
                # Convert 8kHz u-law to 8kHz PCM16
                pcm_8k = self.convert_ulaw_to_pcm(openai_audio)
                # Resample 8kHz PCM16 -> 16kHz PCM16
                playback_audio = self._resample_audio(pcm_8k, 8000, 16000)
            elif output_format == "pcm16":
                # Resample 24kHz PCM16 -> 16kHz PCM16
                playback_audio = self._resample_audio(openai_audio, 24000, 16000)
            else:
                # Fallback: assume already 16kHz PCM
                playback_audio = openai_audio
                
            # Queue to PJSUA2 playback buffer
            await self.sip_server.send_audio_to_rtp(stream_id, playback_audio)
            logger.debug(f"🔊 OPENAI AUDIO DELTA ROUTED TO RTP: {len(openai_audio)} bytes {output_format} -> {len(playback_audio)} bytes PCM16 @ 16kHz")
            
        except Exception as e:
            logger.error(f"❌ Error handling OpenAI audio delta: {e}")

    async def cleanup_connections(self, stream_id: str):
        """Clean up OpenAI connections and buffers"""
        try:
            # Close OpenAI connection
            if stream_id in self.openai_connections:
                openai_ws = self.openai_connections[stream_id]["websocket"]
                try:
                    if hasattr(openai_ws, "closed"):
                        if not openai_ws.closed:
                            await openai_ws.close()
                    else:
                        from websockets.protocol import State
                        if openai_ws.state != State.CLOSED:
                            await openai_ws.close()
                except Exception:
                    try:
                        await openai_ws.close()
                    except Exception:
                        pass
                del self.openai_connections[stream_id]
                logger.info(f"🧹 OPENAI CONNECTION REMOVED: {stream_id}")
            
            # Clean up audio buffers and settings
            if stream_id in self.audio_buffers:
                del self.audio_buffers[stream_id]
                logger.info(f"🧹 AUDIO BUFFER CLEARED: {stream_id}")
            
            if stream_id in self.connection_sample_rates:
                del self.connection_sample_rates[stream_id]
            
            if stream_id in self.connection_chunk_sizes:
                del self.connection_chunk_sizes[stream_id]
                
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")




async def main():
    """Enhanced main function to start the OpenAI Realtime Sales Bot"""
    try:
        # Initialize the enhanced sales bot
        sales_bot = OpenAIRealtimeSalesBot()
        
        # Start the enhanced WebSocket server
        await sales_bot.start_server()
        
    except Exception as e:
        logger.error(f'❌ Enhanced Server Error: {e}')
        raise


if __name__ == "__main__":
    asyncio.run(main()) 