"""
State manager for CTF Agent
Handles shared state between main.py and watcher.py
"""

import json
import os
from typing import Optional, Dict, Any
from datetime import datetime

# Constants
STATE_FILE = "./ctf-logs/state.json"
TOKEN_LOGS_FILE = "./ctf-logs/token_logs.jsonl"
TOKEN_STATE_FILE = "./ctf-logs/token_state.json"
SESSIONS_FILE = "./ctf-logs/sessions.json"


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

def update_state(mode: Optional[str] = None, flag_found: Optional[bool] = None, target_ip: Optional[str] = None):
    """Update specific state values"""
    state = get_state()

    if mode is not None:
        state["mode"] = mode
    if flag_found is not None:
        state["flag_found"] = flag_found
    if target_ip is not None:
        state["target_ip"] = target_ip

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



# Token tracking functions
def append_usage_log(usage: Dict[str, Any], model: str) -> None:
    """Append usage data to logs file (JSONL format)."""
    ensure_state_dir()
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": model,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "cost": usage.get("cost", 0.0),
    }
    with open(TOKEN_LOGS_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


def load_token_state() -> Dict[str, Any]:
    """Load current token state from state file. State is tracked per model."""
    ensure_state_dir()
    if not os.path.exists(TOKEN_STATE_FILE):
        return {"models": {}}

    try:
        with open(TOKEN_STATE_FILE, "r") as f:
            state = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return {"models": {}}

    if "models" not in state:
        return {"models": {}}

    return state


def save_token_state(state: Dict[str, Any]) -> None:
    """Save token state to state file."""
    ensure_state_dir()
    with open(TOKEN_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def update_token_state(usage: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Update running totals per model and save state."""
    state = load_token_state()

    if model not in state["models"]:
        state["models"][model] = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_reasoning_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "request_count": 0,
        }

    model_state = state["models"][model]
    model_state["total_input_tokens"] += usage.get("prompt_tokens", 0)
    model_state["total_output_tokens"] += usage.get("completion_tokens", 0)
    model_state["total_reasoning_tokens"] += usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
    model_state["total_tokens"] += usage.get("total_tokens", 0)
    model_state["total_cost"] += usage.get("cost", 0.0)
    model_state["request_count"] += 1

    save_token_state(state)
    return model_state


def get_model_token_state(model: str) -> Dict[str, Any]:
    """Get token state for a specific model."""
    state = load_token_state()
    return state["models"].get(model, {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_reasoning_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "request_count": 0,
    })


# Session tracking functions
def create_session(model: str, mode: str) -> Dict[str, Any]:
    """Create a new session with unique ID and initial state."""
    import uuid
    session = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": model,
        "mode": mode,
        "commands": [],
        "token_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0
        }
    }
    return session


def update_session_tokens(session: Dict[str, Any], usage: Dict[str, Any]) -> None:
    """Update session token usage with new usage data."""
    session["token_usage"]["input_tokens"] += usage.get("prompt_tokens", 0)
    session["token_usage"]["output_tokens"] += usage.get("completion_tokens", 0)
    session["token_usage"]["total_tokens"] += usage.get("total_tokens", 0)
    session["token_usage"]["total_cost"] += usage.get("cost", 0.0)


def add_session_command(session: Dict[str, Any], command: str, output: str, exit_code: int, reasoning: str = "") -> None:
    """Add a command, its output, and reasoning to the session."""
    session["commands"].append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reasoning": reasoning,
        "command": command,
        "output": output,
        "exit_code": exit_code
    })


def save_session(session: Dict[str, Any]) -> None:
    """Save session to sessions file, including any generated report."""
    ensure_state_dir()

    # Check for generated report in workspace
    report_path = "./ctf-workspace/reports.txt"
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report_content = f.read().strip()
                if report_content:
                    session["report"] = report_content
        except Exception as e:
            print(f"⚠️  Could not read report file: {e}")

    # Load existing sessions
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r") as f:
                sessions = json.load(f)
        except (json.JSONDecodeError, ValueError):
            sessions = []
    else:
        sessions = []

    # Append new session
    sessions.append(session)

    # Save back to file
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)


def get_all_sessions() -> list:
    """Get all saved sessions."""
    ensure_state_dir()
    if not os.path.exists(SESSIONS_FILE):
        return []

    try:
        with open(SESSIONS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return []