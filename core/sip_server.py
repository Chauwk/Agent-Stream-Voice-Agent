#!/usr/bin/env python3
"""
SIP Server for Direct Exotel Trunking Integration
Receives incoming SIP calls from Exotel and bridges with OpenAI Realtime API
Eliminates need for Voicebot Applet, reducing costs

Features:
- Direct SIP trunk support (8kHz/16kHz/24kHz)
- RTP audio streaming with PCM16 codec
- Real-time audio bridging with OpenAI
- Automatic call state management
- NAT traversal support
"""

import asyncio
import logging
import json
import base64
import time
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

try:
    import pjsua as pj
except ImportError:
    pj = None
    
from config import Config

logger = logging.getLogger(__name__)

@dataclass
class SIPCallState:
    """Represents a single SIP call session"""
    call_id: str
    from_uri: str
    to_uri: str
    contact_uri: str
    start_time: float
    openai_connected: bool = False
    audio_buffer: bytes = b""
    sample_rate: int = 16000
    rtp_port: int = 0
    
class SIPServer:
    """SIP Server for receiving calls from Exotel via direct SIP trunk"""
    
    def __init__(self, openai_bot=None):
        """
        Initialize SIP Server for DUAL-MODE operation:
        - INBOUND: Receive calls (IP-based auth)
        - OUTBOUND: Make calls (Digest auth)
        
        Args:
            openai_bot: Reference to OpenAIRealtimeSalesBot instance for audio bridging
        """
        self.openai_bot = openai_bot
        self.sip_account_inbound = None
        self.sip_account_outbound = None
        self.sip_calls: Dict[str, SIPCallState] = {}
        self.audio_buffers: Dict[str, bytes] = {}
        self.pjsua_initialized = False
        self._call_objects: Dict[str, Any] = {}  # Store call objects for RTP I/O
        
        # SIP Configuration from config.py
        self.sip_host = Config.SIP_SERVER_HOST
        self.sip_port = Config.SIP_SERVER_PORT
        self.inbound_enabled = Config.INBOUND_SIP_ENABLED
        self.outbound_enabled = Config.OUTBOUND_SIP_ENABLED
        
        logger.info("🔌 SIP Server initialized (DUAL-MODE)")
        logger.info(f"📍 SIP Server: {self.sip_host}:{self.sip_port}")
        logger.info(f"📥 Inbound vSIP: {'✅ ENABLED' if self.inbound_enabled else '❌ DISABLED'} (IP-based auth)")
        logger.info(f"📤 Outbound SIP: {'✅ ENABLED' if self.outbound_enabled else '❌ DISABLED'} (Digest auth)")

        
    def initialize_pjsua(self):
        """
        Initialize PJSUA2 SIP stack for DUAL-MODE:
        
        INBOUND: Listen on port 5060 for incoming calls (IP-based)
        OUTBOUND: Register with proxy for outbound calls (Digest auth)
        """
        if not pj:
            raise ImportError("pjsua2-py not installed. Run: pip install pjsua2-py")
        
        try:
            # Create library instance
            lib = pj.Lib()
            
            # Init library with default config
            lib.init(
                log_cfg = pj.LogConfig(level=3, callback=self._pj_log_callback),
                ua_cfg = pj.UAConfig(
                    max_calls=Config.MAX_CONCURRENT_CALLS,
                    user_agent="Voice-AI-Bot/1.0 (Dual-Mode SIP)"
                ),
                media_cfg = pj.MediaConfig(
                    clock_rate=16000,
                    snd_clock_rate=16000,
                    has_ioqueue=True,
                    channel_count=1
                )
            )
            
            # Create transport - used for BOTH inbound and outbound
            tp_cfg = pj.TransportConfig(
                port=self.sip_port,
                bound_addr="0.0.0.0",
                public_addr=Config.SIP_PUBLIC_IP if Config.SIP_PUBLIC_IP else self.sip_host
            )
            transport = lib.create_transport(pj.PJSIP_TRANSPORT_UDP, tp_cfg)
            logger.info(f"✅ SIP Transport created: UDP/0.0.0.0:{self.sip_port}")
            logger.info(f"🌐 Public endpoint: {Config.SIP_PUBLIC_IP or self.sip_host}:{self.sip_port}")
            
            # ===== INBOUND ACCOUNT (IP-based auth) =====
            if self.inbound_enabled:
                acc_cfg_inbound = pj.AccountConfig()
                acc_cfg_inbound.id = f"sip:vbot@{self.sip_host}"
                
                self.sip_account_inbound = lib.create_account(
                    acc_cfg_inbound,
                    cb=self._account_callback(mode="inbound")
                )
                logger.info(f"📥 Inbound account created (IP-based)")
            
            # ===== OUTBOUND ACCOUNT (Digest auth) =====
            if self.outbound_enabled:
                if not Config.SIP_USERNAME or not Config.SIP_PASSWORD:
                    raise ValueError("❌ OUTBOUND_SIP_ENABLED but SIP_USERNAME/SIP_PASSWORD not set")
                
                acc_cfg_outbound = pj.AccountConfig()
                acc_cfg_outbound.id = f"sip:{Config.SIP_USERNAME}@{Config.SIP_REALM}"
                acc_cfg_outbound.reg_uri = f"sip:{Config.SIP_REALM}"
                acc_cfg_outbound.proxy = [f"sip:{Config.EXOTEL_OUTBOUND_PROXY}"]
                
                # Add authentication credentials for outbound
                cred = pj.AuthCred(
                    realm=Config.SIP_REALM,
                    scheme="digest",
                    username=Config.SIP_USERNAME,
                    data_type=0,  # PASSWD_PLAIN
                    data=Config.SIP_PASSWORD
                )
                acc_cfg_outbound.cred_info = [cred]
                
                self.sip_account_outbound = lib.create_account(
                    acc_cfg_outbound,
                    cb=self._account_callback(mode="outbound")
                )
                logger.info(f"📤 Outbound account created and registered")
            
            logger.info(f"✅ PJSUA2 initialized successfully (DUAL-MODE)")
            
            self.pjsua_initialized = True
            self.lib = lib
            
            return lib
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize PJSUA: {e}")
            raise
    
    def _pj_log_callback(self, level, str_data, len_data):
        """PJSUA logging callback"""
        if level <= 2:
            logger.warning(f"[PJSUA] {str_data}")
        elif level <= 3:
            logger.info(f"[PJSUA] {str_data}")
        else:
            logger.debug(f"[PJSUA] {str_data}")
    
    def _account_callback(self, mode="inbound"):
        """Create account callback handler for inbound or outbound"""
        class AccountCallback(pj.AccountCallback):
            def __init__(self, parent, mode):
                pj.AccountCallback.__init__(self)
                self.parent = parent
                self.mode = mode
            
            def on_incoming_call(self, call):
                """Handle incoming SIP call (INBOUND only)"""
                if self.mode != "inbound":
                    return
                
                logger.info(f"🔔 INCOMING SIP CALL from {call.info().remote_uri}")
                
                call_callback = self.parent._call_callback()
                call.set_callback(call_callback)
                
                try:
                    prm = pj.CallOpParam(True)
                    prm.statusCode = 200
                    call.answer(prm)
                    logger.info(f"✅ ANSWERED SIP CALL: {call.info().remote_uri}")
                    
                    # Store call state
                    call_id = call.info().call_id
                    call_state = SIPCallState(
                        call_id=call_id,
                        from_uri=call.info().remote_uri,
                        to_uri=call.info().local_uri,
                        contact_uri=call.info().remote_contact,
                        start_time=time.time(),
                        sample_rate=16000,
                        openai_connected=False
                    )
                    self.parent.sip_calls[call_id] = call_state
                    self.parent._call_objects[call_id] = call
                    
                    logger.info(f"📞 Call state stored for {call_id}")
                    logger.info(f"🎵 Sample rate: {call_state.sample_rate}Hz")
                    
                    # Connect to OpenAI
                    asyncio.create_task(
                        self.parent._bridge_call_to_openai(call_id, call)
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Error answering call: {e}")
                    try:
                        call.hangup(pj.CallOpParam(True))
                    except:
                        pass
            
            def on_reg_state(self):
                """Handle registration state (OUTBOUND only)"""
                if self.mode != "outbound":
                    return
                
                acc_info = self.account.info()
                logger.info(f"📤 Outbound account registration state: {acc_info.reg_status_text}")
            
            def on_call_state(self, call):
                """Handle call state changes"""
                call_info = call.info()
                logger.info(f"📞 Call state: {call_info.state_text} - {call_info.remote_uri}")
        
        return AccountCallback(self, mode)
    
    def _call_callback(self):
        """Create call callback handler"""
        class CallCallback(pj.CallCallback):
            def __init__(self, parent):
                pj.CallCallback.__init__(self)
                self.parent = parent
            
            def on_media_state(self, call):
                """Handle media state changes"""
                call_info = call.info()
                logger.info(f"🎵 Media state: {call_info.media_state_text}")
                
                if call_info.media_state == pj.PJSIP_SESSION_MEDIA_ACTIVE:
                    logger.info(f"✅ RTP STREAM ACTIVE for call {call_info.call_id}")
            
            def on_dtmf_digit(self, call, digit):
                """Handle DTMF digits"""
                logger.info(f"🔢 DTMF digit received: {digit}")
            
            def on_call_transfer_status(self, call, st_code, st_text, final, p_cont):
                """Handle call transfer"""
                logger.info(f"📞 Call transfer: {st_code} {st_text}")
                return True
        
        return CallCallback(self)
    
    async def _bridge_call_to_openai(self, call_id: str, call):
        """Bridge a SIP call with OpenAI Realtime API"""
        try:
            if not self.openai_bot:
                logger.error("❌ OpenAI bot not available for bridging")
                call.hangup(pj.CallOpParam(True))
                return
            
            call_state = self.sip_calls[call_id]
            
            logger.info(f"🌉 BRIDGING SIP CALL {call_id} to OpenAI")
            
            # Connect to OpenAI (same as WebSocket flow)
            await self.openai_bot.connect_to_openai_enhanced(call_id)
            
            call_state.openai_connected = True
            logger.info(f"✅ OpenAI connection established for {call_id}")
            
            # Start audio receiving loop
            await self._receive_rtp_audio(call_id, call)
            
        except Exception as e:
            logger.error(f"❌ Error bridging call to OpenAI: {e}")
            try:
                call.hangup(pj.CallOpParam(True))
            except:
                pass
            finally:
                await self.cleanup_call(call_id)
    
    async def _receive_rtp_audio(self, call_id: str, call):
        """Receive RTP audio stream and forward to OpenAI - Full media server implementation"""
        try:
            call_state = self.sip_calls[call_id]
            
            # Get audio media from SIP call
            aud_med = call.get_audio_media()
            if not aud_med:
                logger.error(f"❌ No audio media available for {call_id}")
                return
            
            logger.info(f"🎵 RTP Audio media active for {call_id}")
            
            # Create audio port for receiving RTP packets
            # This hooks into PJSUA2's media port API
            audio_port = aud_med.get_port()
            if not audio_port:
                logger.error(f"❌ Could not get audio port for {call_id}")
                return
            
            logger.info(f"📡 Audio port {audio_port} acquired for RTP reception")
            
            # RTP audio receiving loop - process incoming audio frames
            chunk_size_ms = 20  # 20ms frames (standard for VoIP)
            chunk_size_bytes = int(call_state.sample_rate * chunk_size_ms / 1000) * 2  # 16-bit PCM
            
            while call_state.openai_connected and call_id in self.sip_calls:
                try:
                    # Get frame from audio port (this is where RTP packets are parsed)
                    frame = audio_port.get_frame() if hasattr(audio_port, 'get_frame') else None
                    
                    if frame and frame.buf:
                        # Frame contains decoded RTP audio data (PCM16)
                        audio_data = bytes(frame.buf[:frame.size])
                        
                        logger.debug(f"📥 Received {len(audio_data)} bytes RTP audio for {call_id}")
                        
                        # Add to audio buffer
                        call_state.audio_buffer += audio_data
                        
                        # Send to OpenAI when we have enough data
                        if len(call_state.audio_buffer) >= chunk_size_bytes:
                            chunk = call_state.audio_buffer[:chunk_size_bytes]
                            call_state.audio_buffer = call_state.audio_buffer[chunk_size_bytes:]
                            
                            # Send audio chunk to OpenAI
                            if self.openai_bot:
                                await self.openai_bot.send_audio_to_openai(
                                    call_id, 
                                    chunk, 
                                    sample_rate=call_state.sample_rate
                                )
                                logger.debug(f"📤 Forwarded {len(chunk)} bytes to OpenAI")
                    
                    # Non-blocking frame fetch with small sleep
                    await asyncio.sleep(0.010)  # 10ms polling interval
                    
                except Exception as e:
                    logger.error(f"❌ Error receiving RTP audio frame: {e}")
                    await asyncio.sleep(0.020)
                    continue
            
        except Exception as e:
            logger.error(f"❌ Error in RTP audio receiving: {e}")
        finally:
            await self.cleanup_call(call_id)
    
    async def send_audio_to_rtp(self, call_id: str, audio: bytes):
        """Send audio back to SIP caller via RTP - Full media server implementation"""
        try:
            if call_id not in self.sip_calls:
                logger.warning(f"⚠️ Call {call_id} not found for RTP send")
                return
            
            call_state = self.sip_calls[call_id]
            
            # Get audio media from call
            if not hasattr(self, '_call_objects') or call_id not in self._call_objects:
                logger.error(f"❌ Call object not available for {call_id}")
                return
            
            call = self._call_objects[call_id]
            aud_med = call.get_audio_media()
            
            if not aud_med:
                logger.error(f"❌ No audio media for sending to {call_id}")
                return
            
            # Get audio port for sending (RTP transmission)
            audio_port = aud_med.get_port()
            if not audio_port:
                logger.error(f"❌ Could not get audio port for RTP send {call_id}")
                return
            
            # Send audio frame via RTP (PJSUA2 handles RTP packet construction and transmission)
            if hasattr(audio_port, 'put_frame'):
                try:
                    # Create frame object compatible with PJSUA2
                    # Audio is PCM16, will be encoded per SDP negotiation (G.711 ulaw/alaw or raw PCM)
                    frame_data = pj.AudioMediaFrame()
                    frame_data.buf = audio
                    frame_data.size = len(audio)
                    frame_data.type = 0  # PJMEDIA_FRAME_TYPE_AUDIO
                    
                    # Put frame into port (transmits via RTP)
                    audio_port.put_frame(frame_data)
                    
                    logger.debug(f"📤 Sent {len(audio)} bytes to RTP/UDP for {call_id}")
                    
                except Exception as e:
                    logger.error(f"❌ Error putting audio frame to RTP: {e}")
            else:
                logger.warning(f"⚠️ Audio port doesn't support put_frame for {call_id}")
        
        except Exception as e:
            logger.error(f"❌ Error sending audio to RTP: {e}")
    
    async def make_outbound_call(self, phone_number: str, context: dict = None) -> str:
        """
        Make an outbound call to a phone number
        
        Args:
            phone_number: Target phone number (e.g., "+919876543210" or "919876543210")
            context: Optional context dict with customer info for bot
            
        Returns:
            call_id: The SIP call ID, or None if failed
            
        Example:
            call_id = await sip_server.make_outbound_call("+919876543210")
        """
        try:
            if not self.outbound_enabled or not self.sip_account_outbound:
                logger.error(f"❌ Outbound SIP not enabled or not registered")
                return None
            
            # Format phone number for SIP
            if not phone_number.startswith("+"):
                phone_number = "+" + phone_number
            
            # Create SIP URI
            sip_uri = f"sip:{phone_number}@exotel.com"
            
            logger.info(f"📤 Making outbound call to {phone_number}")
            logger.info(f"📍 SIP URI: {sip_uri}")
            
            # Create call parameters
            call_prm = pj.CallOpParam(True)
            
            # Make the call
            call = self.sip_account_outbound.make_call(sip_uri, call_prm)
            
            if not call:
                logger.error(f"❌ Failed to create outbound call")
                return None
            
            call_id = call.info().call_id
            
            # Store call state
            call_state = SIPCallState(
                call_id=call_id,
                from_uri=self.sip_account_outbound.info().uri,
                to_uri=sip_uri,
                contact_uri=phone_number,
                start_time=time.time(),
                sample_rate=16000,
                openai_connected=False
            )
            self.sip_calls[call_id] = call_state
            self._call_objects[call_id] = call
            
            # Set call callback
            call_callback = self._call_callback()
            call.set_callback(call_callback)
            
            logger.info(f"✅ Outbound call initiated: {call_id}")
            logger.info(f"📞 Target: {phone_number}")
            
            # Wait for call to be connected (with timeout)
            max_wait = 30  # 30 seconds
            elapsed = 0
            while elapsed < max_wait:
                call_info = call.info()
                if call_info.state == pj.PJSIP_INV_STATE_CONFIRMED:
                    logger.info(f"✅ Outbound call CONNECTED: {call_id}")
                    
                    # Connect to OpenAI
                    await self.openai_bot.connect_to_openai_enhanced(call_id)
                    call_state.openai_connected = True
                    
                    # Start audio bridge
                    await self._receive_rtp_audio(call_id, call)
                    break
                elif call_info.state >= pj.PJSIP_INV_STATE_DISCONNECTED:
                    logger.error(f"❌ Outbound call failed: {call_info.state_text}")
                    return None
                
                await asyncio.sleep(0.5)
                elapsed += 0.5
            
            return call_id
            
        except Exception as e:
            logger.error(f"❌ Error making outbound call: {e}")
            return None
    

        """Clean up SIP call resources"""
        try:
            if call_id in self.sip_calls:
                call_state = self.sip_calls[call_id]
                
                # Hangup SIP call
                if call_id in self._call_objects:
                    call = self._call_objects[call_id]
                    try:
                        call.hangup(pj.CallOpParam(True))
                        logger.info(f"📞 SIP call {call_id} hung up")
                    except:
                        pass
                    del self._call_objects[call_id]
                
                # Disconnect from OpenAI
                if call_state.openai_connected and self.openai_bot:
                    await self.openai_bot.cleanup_connections(call_id)
                
                # Remove call state
                del self.sip_calls[call_id]
                
                duration = time.time() - call_state.start_time
                logger.info(f"🧹 Cleaned up SIP call {call_id} (duration: {duration:.1f}s)")
                
        except Exception as e:
            logger.error(f"❌ Error cleaning up call: {e}")
    
    async def start(self):
        """Start SIP server"""
        try:
            if not self.pjsua_initialized:
                self.initialize_pjsua()
            
            # Start PJSUA library in a thread
            threading.Thread(target=self._pjsua_event_loop, daemon=True).start()
            
            logger.info(f"🚀 SIP Server started on {self.sip_host}:{self.sip_port}")
            logger.info("📞 Waiting for incoming calls from Exotel SIP trunk...")
            
        except Exception as e:
            logger.error(f"❌ Failed to start SIP server: {e}")
            raise
    
    def _pjsua_event_loop(self):
        """PJSUA event processing loop"""
        try:
            while True:
                self.lib.handle_events(10)  # Process events every 10ms
                time.sleep(0.01)
        except Exception as e:
            logger.error(f"❌ PJSUA event loop error: {e}")
    
    async def stop(self):
        """Stop SIP server and cleanup"""
        try:
            # Hangup all active calls
            for call_id in list(self.sip_calls.keys()):
                await self.cleanup_call(call_id)
            
            # Destroy PJSUA library
            if self.pjsua_initialized and hasattr(self, 'lib'):
                self.lib.destroy()
                logger.info("✅ PJSUA library destroyed")
            
            logger.info("🛑 SIP Server stopped")
            
        except Exception as e:
            logger.error(f"❌ Error stopping SIP server: {e}")
