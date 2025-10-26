"""Cleanup and signal handling utilities for graceful shutdown"""
import sys
import signal
import time
from src.utils.state_manager import save_session
from src.utils.vpn import disconnect_from_hackthebox
from src.utils.session_utils import display_session_summary

# Global variables for cleanup in signal handler
_cleanup_data = {
    'container': None,
    'vpn_connected': False,
    'session': None,
    'iteration': 0,
    'start_time': None,
    'model': None
}


def signal_handler(sig, frame):
    """Handle interrupt signal (Ctrl+C) for graceful shutdown"""
    print('\\n\\n🛑 Interrupting program...')
    print('👋 Cleaning up...')

    # Disconnect VPN if connected
    if _cleanup_data['vpn_connected'] and _cleanup_data['container']:
        print('🔌 Disconnecting VPN...')
        disconnect_from_hackthebox(_cleanup_data['container'])

    # Save session if exists
    if _cleanup_data['session']:
        print('💾 Saving session...')
        save_session(_cleanup_data['session'])

    print('✅ Cleanup complete.')
    
    # Display session summary if we have the necessary data
    if _cleanup_data['session'] and _cleanup_data['start_time'] and _cleanup_data['model']:
        elapsed_seconds = time.time() - _cleanup_data['start_time']
        display_session_summary(
            _cleanup_data['session'],
            _cleanup_data['iteration'],
            elapsed_seconds,
            _cleanup_data['model']
        )
    
    sys.exit(0)


def register_signal_handler():
    """Register the signal handler for graceful shutdown"""
    signal.signal(signal.SIGINT, signal_handler)


def set_container(container):
    """Store container reference for cleanup"""
    _cleanup_data['container'] = container


def set_vpn_connected(connected: bool):
    """Update VPN connection status for cleanup"""
    _cleanup_data['vpn_connected'] = connected


def set_session(session: dict):
    """Store session reference for cleanup"""
    _cleanup_data['session'] = session


def is_vpn_connected() -> bool:
    """Check if VPN is currently connected"""
    return _cleanup_data['vpn_connected']


def set_iteration(iteration: int):
    """Store current iteration count for cleanup"""
    _cleanup_data['iteration'] = iteration


def set_start_time(start_time: float):
    """Store session start time for cleanup"""
    _cleanup_data['start_time'] = start_time


def set_model(model: str):
    """Store model name for cleanup"""
    _cleanup_data['model'] = model
