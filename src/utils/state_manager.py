"""
State manager for CTF Agent
Handles shared state between main.py and watcher.py
"""

import json
import os
from typing import Optional

STATE_FILE = "./ctf-logs/state.json"

def ensure_state_dir():
    """Create state directory if it doesn't exist"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

def init_state(mode: str = "auto"):
    """Initialize state file with default values"""
    ensure_state_dir()
    state = {
        "mode": mode,  # "auto" or "semi-auto"
        "flag_found": False,
        "last_updated": None
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state

def get_state() -> dict:
    """Read current state from file"""
    ensure_state_dir()
    if not os.path.exists(STATE_FILE):
        return init_state()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return init_state()

def update_state(mode: Optional[str] = None, flag_found: Optional[bool] = None):
    """Update specific state values"""
    state = get_state()

    if mode is not None:
        state["mode"] = mode
    if flag_found is not None:
        state["flag_found"] = flag_found

    import time
    state["last_updated"] = time.strftime('%Y-%m-%d %H:%M:%S')

    ensure_state_dir()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    return state

def get_mode() -> str:
    """Get current mode"""
    return get_state().get("mode", "auto")

def set_mode(mode: str):
    """Set mode (auto or semi-auto)"""
    update_state(mode=mode)