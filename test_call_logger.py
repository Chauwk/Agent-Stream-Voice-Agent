#!/usr/bin/env python3
"""
Call Test Logger - Monitor bot during test calls
Shows real-time metrics while you're testing
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

# Simple test call recorder
class CallTestLogger:
    def __init__(self, filename="test_calls.log"):
        self.filename = filename
        self.calls = []
        self.start_time = datetime.now()
        self.current_call = None
    
    def start_inbound_call(self, phone_number="Unknown"):
        """Log start of inbound call"""
        self.current_call = {
            'type': 'inbound',
            'from': phone_number,
            'started_at': datetime.now().isoformat(),
            'events': [],
            'metrics': {}
        }
        self.calls.append(self.current_call)
        self._print_header(f"📥 INBOUND CALL from {phone_number}")
        self._log_event("call_started", f"Call initiated at {datetime.now().strftime('%H:%M:%S')}")
    
    def start_outbound_call(self, phone_number):
        """Log start of outbound call"""
        self.current_call = {
            'type': 'outbound',
            'to': phone_number,
            'started_at': datetime.now().isoformat(),
            'events': [],
            'metrics': {}
        }
        self.calls.append(self.current_call)
        self._print_header(f"📤 OUTBOUND CALL to {phone_number}")
        self._log_event("call_initiated", f"Call initiated at {datetime.now().strftime('%H:%M:%S')}")
    
    def log_bot_answered(self, answer_time_ms):
        """Log bot answered"""
        self._log_event("bot_answered", f"Bot answered in {answer_time_ms}ms")
        if self.current_call:
            self.current_call['metrics']['answer_time_ms'] = answer_time_ms
        print(f"✅ Bot answered: {answer_time_ms}ms")
    
    def log_greeting_played(self):
        """Log greeting played"""
        self._log_event("greeting_played", "Greeting played to caller")
        print(f"🎤 Greeting played")
    
    def log_audio_received(self, size_bytes, duration_ms):
        """Log audio received"""
        self._log_event("audio_received", f"Received {size_bytes} bytes ({duration_ms}ms)")
        if not self.current_call:
            return
        if 'audio_chunks' not in self.current_call['metrics']:
            self.current_call['metrics']['audio_chunks'] = []
        self.current_call['metrics']['audio_chunks'].append({
            'size': size_bytes,
            'duration': duration_ms
        })
    
    def log_bot_response(self, latency_ms, text_snippet=""):
        """Log bot response"""
        self._log_event("bot_response", f"Response in {latency_ms}ms: {text_snippet}")
        if self.current_call:
            self.current_call['metrics']['response_latency_ms'] = latency_ms
        print(f"💬 Bot response: {latency_ms}ms")
    
    def log_audio_quality(self, clarity=None, echo=None, noise=None):
        """Log audio quality metrics"""
        msg = f"Quality - Clarity: {clarity}, Echo: {echo}, Noise: {noise}"
        self._log_event("audio_quality", msg)
        if self.current_call:
            self.current_call['metrics']['quality'] = {
                'clarity': clarity,
                'echo': echo,
                'noise': noise
            }
        print(f"📊 {msg}")
    
    def log_call_ended(self, duration_sec, reason="normal"):
        """Log call ended"""
        self._log_event("call_ended", f"Call ended after {duration_sec}s ({reason})")
        if self.current_call:
            self.current_call['metrics']['duration_sec'] = duration_sec
            self.current_call['metrics']['end_reason'] = reason
        print(f"📞 Call ended: {duration_sec}s ({reason})")
        print()
    
    def log_issue(self, issue_type, description):
        """Log an issue"""
        self._log_event("issue", f"[{issue_type}] {description}")
        print(f"⚠️  ISSUE: [{issue_type}] {description}")
    
    def _log_event(self, event_type, description):
        """Internal: log an event"""
        if not self.current_call:
            return
        self.current_call['events'].append({
            'time': datetime.now().isoformat(),
            'type': event_type,
            'description': description
        })
    
    def _print_header(self, text):
        """Print formatted header"""
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60)
    
    def save_report(self):
        """Save all test results to file"""
        report = {
            'test_session': {
                'started_at': self.start_time.isoformat(),
                'ended_at': datetime.now().isoformat(),
                'total_calls': len(self.calls)
            },
            'calls': self.calls
        }
        
        with open(self.filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n✅ Test report saved to: {self.filename}")
        return self.filename
    
    def print_summary(self):
        """Print summary of all tests"""
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        if not self.calls:
            print("No calls recorded")
            return
        
        total_calls = len(self.calls)
        inbound_calls = [c for c in self.calls if c['type'] == 'inbound']
        outbound_calls = [c for c in self.calls if c['type'] == 'outbound']
        
        print(f"\nTotal calls: {total_calls}")
        print(f"  - Inbound: {len(inbound_calls)}")
        print(f"  - Outbound: {len(outbound_calls)}")
        
        # Average metrics
        answer_times = [c['metrics'].get('answer_time_ms', 0) for c in self.calls if 'answer_time_ms' in c['metrics']]
        response_times = [c['metrics'].get('response_latency_ms', 0) for c in self.calls if 'response_latency_ms' in c['metrics']]
        durations = [c['metrics'].get('duration_sec', 0) for c in self.calls if 'duration_sec' in c['metrics']]
        
        if answer_times:
            print(f"\nAnswer times (avg): {sum(answer_times)/len(answer_times):.0f}ms")
        if response_times:
            print(f"Response latency (avg): {sum(response_times)/len(response_times):.0f}ms")
        if durations:
            print(f"Call duration (avg): {sum(durations)/len(durations):.1f}s")
        
        print("\n✅ Detailed report saved to: " + self.filename)


# Example usage
def example_inbound_test():
    """Example: Log an inbound test call"""
    logger = CallTestLogger("test_calls_example.log")
    
    # Simulate inbound call
    logger.start_inbound_call("+919876543210")
    logger.log_bot_answered(2500)
    logger.log_greeting_played()
    
    time.sleep(1)
    
    logger.log_audio_received(512, 500)
    logger.log_bot_response(800, "Hi, thanks for calling. How can I help you?")
    
    logger.log_audio_received(512, 500)
    logger.log_bot_response(950, "We offer great services for your business...")
    
    logger.log_audio_quality(clarity=9, echo=9, noise=8)
    logger.log_call_ended(25, "normal")
    
    logger.print_summary()
    logger.save_report()


if __name__ == "__main__":
    print("📋 Call Test Logger - Example")
    print("=" * 60)
    print("\nUsage in your test code:")
    print("""
    from test_call_logger import CallTestLogger
    
    logger = CallTestLogger()
    logger.start_inbound_call("+919876543210")
    logger.log_bot_answered(2500)
    logger.log_greeting_played()
    ...
    logger.log_call_ended(25, "normal")
    logger.print_summary()
    logger.save_report()
    """)
    
    print("\nRunning example...\n")
    example_inbound_test()
