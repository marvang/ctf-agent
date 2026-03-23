"""
State manager for CTF Agent.

`session["events"]` is the canonical replay log.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any


def _utc_timestamp() -> str:
    """Return an RFC3339-like UTC timestamp string."""
    return datetime.utcnow().isoformat() + "Z"


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached copy of a mapping suitable for JSON serialization."""
    return copy.deepcopy(dict(value))


def create_session(model: str, chap_enabled: bool = False) -> dict[str, Any]:
    """Create a new session with unique ID and initial state."""
    session = {
        "schema_version": 3,
        "id": str(uuid.uuid4()),
        "timestamp": _utc_timestamp(),
        "model": model,
        "events": [],
        "context": {},
        "metrics": {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_reasoning_tokens": 0,
            "total_cached_tokens": 0,
            "total_audio_tokens": 0,
            "total_cost": 0.0,
            "total_upstream_inference_cost": 0.0,
            "total_iterations": 0,
            "total_time": 0.0,
        },
        "chap_enabled": chap_enabled,
        "agent_number": 0,
        "relay_protocols": [],
        "relay_triggers": [],
    }
    return session


def set_session_context(session: dict[str, Any], **context: Any) -> None:
    """Store replay and artifact metadata on the session."""
    session.setdefault("context", {})
    for key, value in context.items():
        if value is not None:
            session["context"][key] = value


def update_session_tokens(session: dict[str, Any], usage: dict[str, Any]) -> None:
    """Update session token usage with new usage data."""
    session["metrics"]["total_input_tokens"] += usage.get("prompt_tokens") or 0
    session["metrics"]["total_output_tokens"] += usage.get("completion_tokens") or 0
    session["metrics"]["total_tokens"] += usage.get("total_tokens") or 0
    session["metrics"]["total_reasoning_tokens"] += (
        usage.get("completion_tokens_details", {}).get("reasoning_tokens") or 0
    )
    session["metrics"]["total_cached_tokens"] += usage.get("prompt_tokens_details", {}).get("cached_tokens") or 0
    session["metrics"]["total_audio_tokens"] += usage.get("prompt_tokens_details", {}).get("audio_tokens") or 0
    session["metrics"]["total_cost"] += usage.get("cost") or 0.0
    session["metrics"]["total_upstream_inference_cost"] += (
        usage.get("cost_details", {}).get("upstream_inference_cost") or 0.0
    )


def build_assistant_message(reasoning: str, shell_command: str) -> dict[str, str]:
    """Build the assistant message shape stored in the replay log."""
    return {
        "role": "assistant",
        "content": json.dumps({"reasoning": reasoning, "shell_command": shell_command}),
    }


def append_session_event(
    session: dict[str, Any],
    *,
    stream: str,
    tag: str,
    message: Mapping[str, Any] | None = None,
    parsed: Mapping[str, Any] | None = None,
    iteration: int | None = None,
    agent_number: int | None = None,
    model_name: str | None = None,
    usage: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    session_path: str | Path | None = None,
) -> dict[str, Any]:
    """Append a replay event and optionally flush the session checkpoint."""
    events = session.setdefault("events", [])
    event: dict[str, Any] = {
        "event_index": len(events),
        "timestamp": _utc_timestamp(),
        "stream": stream,
        "tag": tag,
        "agent_number": session.get("agent_number", 0) if agent_number is None else agent_number,
        "model_name": session.get("model", "") if model_name is None else model_name,
    }
    if iteration is not None:
        event["iteration"] = iteration
    if message is not None:
        event["message"] = _copy_mapping(message)
    if parsed is not None:
        event["parsed"] = _copy_mapping(parsed)
    if usage is not None:
        event["usage"] = _copy_mapping(usage)
    if metadata is not None:
        event["metadata"] = _copy_mapping(metadata)

    events.append(event)
    if session_path is not None:
        persist_session(session, session_path)
    return event


def increment_agent_number(session: dict[str, Any]) -> None:
    """Increment the agent number for relay handoff."""
    session["agent_number"] += 1


def add_relay_protocol(session: dict[str, Any], protocol: dict[str, Any]) -> None:
    """Add a relay protocol to the session's protocol list."""
    session.setdefault("relay_protocols", []).append(protocol)


def get_current_agent_tokens(session: dict[str, Any]) -> int:
    """
    Calculate tokens used by current agent only (excluding previous relays).

    Args:
        session: Session object containing metrics and relay protocols

    Returns:
        Token count for current agent since last relay (or session start)
    """
    current_total = session["metrics"]["total_tokens"]

    if not session.get("relay_protocols"):
        return int(current_total)

    last_protocol = session["relay_protocols"][-1]
    tokens_at_last_relay = last_protocol["metrics"]["snapshot_total_tokens"]
    return int(current_total - tokens_at_last_relay)


def persist_session(session: dict[str, Any], session_path: str | Path) -> None:
    """Atomically persist the current session checkpoint to disk."""
    path = Path(session_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(session, handle, indent=2)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
