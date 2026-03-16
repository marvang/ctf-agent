"""
State manager for CTF Agent.

`session["events"]` is the canonical replay log.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping


def _utc_timestamp() -> str:
    """Return an RFC3339-like UTC timestamp string."""
    return datetime.utcnow().isoformat() + "Z"


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached copy of a mapping suitable for JSON serialization."""
    return copy.deepcopy(dict(value))


def create_session(model: str, chap_enabled: bool = False) -> Dict[str, Any]:
    """Create a new session with unique ID and initial state."""
    import uuid

    session = {
        "schema_version": 2,
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


def set_session_context(session: Dict[str, Any], **context: Any) -> None:
    """Store replay and artifact metadata on the session."""
    session.setdefault("context", {})
    for key, value in context.items():
        if value is not None:
            session["context"][key] = value


def update_session_tokens(session: Dict[str, Any], usage: Dict[str, Any]) -> None:
    """Update session token usage with new usage data."""
    session["metrics"]["total_input_tokens"] += usage.get("prompt_tokens") or 0
    session["metrics"]["total_output_tokens"] += usage.get("completion_tokens") or 0
    session["metrics"]["total_tokens"] += usage.get("total_tokens") or 0
    session["metrics"]["total_reasoning_tokens"] += (
        usage.get("completion_tokens_details", {}).get("reasoning_tokens") or 0
    )
    session["metrics"]["total_cached_tokens"] += (
        usage.get("prompt_tokens_details", {}).get("cached_tokens") or 0
    )
    session["metrics"]["total_audio_tokens"] += (
        usage.get("prompt_tokens_details", {}).get("audio_tokens") or 0
    )
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
    session: Dict[str, Any],
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
) -> Dict[str, Any]:
    """Append a replay event and optionally flush the session checkpoint."""
    events = session.setdefault("events", [])
    event: Dict[str, Any] = {
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


def increment_agent_number(session: Dict[str, Any]) -> None:
    """Increment the agent number for relay handoff."""
    session["agent_number"] += 1


def add_relay_protocol(session: Dict[str, Any], protocol: Dict[str, Any]) -> None:
    """Add a relay protocol to the session's protocol list."""
    session.setdefault("relay_protocols", []).append(protocol)


def get_current_agent_tokens(session: Dict[str, Any]) -> int:
    """
    Calculate tokens used by current agent only (excluding previous relays).

    Args:
        session: Session object containing metrics and relay protocols

    Returns:
        Token count for current agent since last relay (or session start)
    """
    current_total = session["metrics"]["total_tokens"]

    if not session.get("relay_protocols"):
        return current_total

    last_protocol = session["relay_protocols"][-1]
    tokens_at_last_relay = last_protocol["metrics"]["snapshot_total_tokens"]
    return current_total - tokens_at_last_relay


def persist_session(session: Dict[str, Any], session_path: str | Path) -> None:
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


def _context_value(
    session: Mapping[str, Any],
    key: str,
    override: Any,
) -> Any:
    """Resolve an artifact field from an override or stored session context."""
    if override is not None:
        return override
    context = session.get("context", {})
    if isinstance(context, Mapping):
        return context.get(key)
    return None


def _coerce_bool(value: Any) -> bool:
    """Normalize JSON-ish booleans, including legacy string values."""
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def build_used_prompts_payload(
    session: Mapping[str, Any],
    *,
    mode: str,
    experiment_id: str | None = None,
    challenge_name: str | None = None,
    model_name: str | None = None,
    chap_enabled: bool | None = None,
    chap_auto_trigger: bool | None = None,
    environment_mode: str | None = None,
    target_ip: str | None = None,
) -> dict[str, Any]:
    """Build the legacy `used_prompts.json` payload from canonical events."""
    events = session.get("events", [])
    if not isinstance(events, list) or not events:
        raise ValueError("Session does not contain replay events")

    resolved_experiment_id = _context_value(session, "experiment_id", experiment_id)
    resolved_challenge_name = _context_value(session, "challenge_name", challenge_name)
    resolved_model_name = _context_value(session, "model_name", model_name) or session.get("model")
    resolved_chap_enabled = _context_value(session, "chap_enabled", chap_enabled)
    if resolved_chap_enabled is None:
        resolved_chap_enabled = session.get("chap_enabled")
    resolved_chap_auto_trigger = _context_value(session, "chap_auto_trigger", chap_auto_trigger)
    resolved_environment_mode = _context_value(session, "environment_mode", environment_mode)
    resolved_target_ip = _context_value(session, "target_ip", target_ip)
    chap_enabled_value = _coerce_bool(resolved_chap_enabled)
    if chap_enabled_value and resolved_chap_auto_trigger is None:
        raise ValueError("CHAP-enabled session is missing chap_auto_trigger metadata")
    chap_auto_trigger_value = _coerce_bool(resolved_chap_auto_trigger)

    system_prompt = None
    initial_messages: list[dict[str, Any]] = []
    protocol_generator_system_prompt = None
    relay_initial_messages: list[dict[str, Any]] = []

    for event in events:
        tag = event.get("tag")
        message = event.get("message")
        if not isinstance(message, Mapping):
            continue

        if tag == "initial_system_prompt" and system_prompt is None:
            system_prompt = message.get("content")
        elif tag == "initial_user_prompt":
            initial_messages.append(_copy_mapping(message))
        elif tag == "protocol_generator_system_prompt_template" and protocol_generator_system_prompt is None:
            protocol_generator_system_prompt = message.get("content")
        elif tag == "protocol_request_system_prompt" and protocol_generator_system_prompt is None:
            protocol_generator_system_prompt = message.get("content")
        elif tag == "relay_user_prompt":
            relay_number = None
            metadata = event.get("metadata")
            if isinstance(metadata, Mapping):
                relay_number = metadata.get("relay_number")
            relay_initial_messages.append(
                {
                    "relay_number": relay_number,
                    "user_content": message.get("content"),
                }
            )

    prompt_payload = {
        "experiment_id": resolved_experiment_id,
        "challenge_name": resolved_challenge_name,
        "model_name": resolved_model_name,
        "chap_enabled": chap_enabled_value,
        "chap_auto_trigger": chap_auto_trigger_value,
        "system_prompt": system_prompt,
        "initial_messages": initial_messages,
    }

    if mode == "interactive":
        prompt_payload["environment_mode"] = resolved_environment_mode
        prompt_payload["target_ip"] = resolved_target_ip

    if chap_enabled_value:
        if protocol_generator_system_prompt is not None:
            prompt_payload["protocol_generator_system_prompt"] = protocol_generator_system_prompt
        prompt_payload["relay_initial_messages"] = relay_initial_messages

    return prompt_payload

