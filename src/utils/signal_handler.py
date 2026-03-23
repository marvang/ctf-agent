"""Cleanup and signal handling utilities for graceful shutdown"""

import signal
import sys
import time
from collections.abc import Callable
from types import FrameType
from typing import Any

from docker.models.containers import Container

from src.utils.session_utils import display_session_summary
from src.utils.vpn import disconnect_vpn

# Global variables for cleanup in signal handler
_cleanup_data: dict[str, Any] = {
    "container": None,
    "vpn_connected": False,
    "vpn_env": "private",
    "session": None,
    "iteration": 0,
    "start_time": None,
    "model": None,
    "save_callback": None,
    "cleanup_callback": None,
    "session_dir": None,
}


def signal_handler(sig: int, frame: FrameType | None) -> None:
    """Handle interrupt signal (Ctrl+C) for graceful shutdown"""
    print("\\n\\n👋 Shutting down...")

    # Save session via callback if registered
    if _cleanup_data["save_callback"]:
        print("💾 Saving session...")
        _cleanup_data["save_callback"]()

    # Run shared cleanup if registered, otherwise fall back to VPN disconnect only.
    if _cleanup_data["cleanup_callback"]:
        _cleanup_data["cleanup_callback"]()
    elif _cleanup_data["vpn_connected"] and _cleanup_data["container"]:
        disconnect_vpn(_cleanup_data["container"], _cleanup_data["vpn_env"])

    # The main loop finally block will print the summary once save_callback is registered.
    if (
        not _cleanup_data["save_callback"]
        and _cleanup_data["session"]
        and _cleanup_data["start_time"]
        and _cleanup_data["model"]
    ):
        elapsed_seconds = time.time() - _cleanup_data["start_time"]
        display_session_summary(
            _cleanup_data["session"], _cleanup_data["iteration"], elapsed_seconds, _cleanup_data["model"]
        )

    sys.exit(0)


def register_signal_handler() -> None:
    """Register the signal handler for graceful shutdown"""
    signal.signal(signal.SIGINT, signal_handler)


def set_container(container: Container) -> None:
    """Store container reference for cleanup"""
    _cleanup_data["container"] = container


def set_vpn_connected(connected: bool) -> None:
    """Update VPN connection status for cleanup"""
    _cleanup_data["vpn_connected"] = connected


def set_session(session: dict[str, Any]) -> None:
    """Store session reference for cleanup"""
    _cleanup_data["session"] = session


def is_vpn_connected() -> bool:
    """Check if VPN is currently connected"""
    return bool(_cleanup_data["vpn_connected"])


def set_iteration(iteration: int) -> None:
    """Store current iteration count for cleanup"""
    _cleanup_data["iteration"] = iteration


def set_start_time(start_time: float) -> None:
    """Store session start time for cleanup"""
    _cleanup_data["start_time"] = start_time


def set_model(model: str) -> None:
    """Store model name for cleanup"""
    _cleanup_data["model"] = model


def set_vpn_env(env: str) -> None:
    """Store VPN environment type for cleanup"""
    _cleanup_data["vpn_env"] = env


def set_save_callback(callback: Callable[[], None]) -> None:
    """Store save callback for interrupt handler"""
    _cleanup_data["save_callback"] = callback


def set_cleanup_callback(callback: Callable[[], None]) -> None:
    """Store cleanup callback for interrupt handler"""
    _cleanup_data["cleanup_callback"] = callback


def set_session_dir(path: str) -> None:
    """Store session directory path for interrupt handler"""
    _cleanup_data["session_dir"] = path
