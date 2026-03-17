"""
Replay helpers for reconstructing OpenRouter call payloads from session logs.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from src.chap_utils.protocol_generator import rebuild_protocol_request_messages

MAIN_AGENT_CALL_TAGS = {
    "assistant_auto_relay_discarded",
    "assistant_command",
    "assistant_empty_command",
    "assistant_exit",
    "assistant_relay",
}


def _copy_message(message: Mapping[str, Any]) -> dict[str, Any]:
    """Detach a message mapping for replay output."""
    return copy.deepcopy(dict(message))


def _get_session_events(session: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return the canonical event list or raise if the session is invalid."""
    events = session.get("events")
    if not isinstance(events, list):
        raise ValueError("Session does not contain a replay event list")
    return [event for event in events if isinstance(event, Mapping)]


def _resolve_event(
    session: Mapping[str, Any],
    *,
    event_index: int,
) -> Mapping[str, Any]:
    """Look up a replay event by index with validation."""
    events = _get_session_events(session)
    for event in events:
        if event.get("event_index") == event_index:
            return event
    raise ValueError(f"Session does not contain event_index={event_index}")


def list_replayable_model_calls(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return all replayable OpenRouter calls in chronological order."""
    calls: list[dict[str, Any]] = []
    stream_call_counts: dict[str, int] = {}

    for event in _get_session_events(session):
        stream = event.get("stream")
        tag = event.get("tag")

        if (stream == "main_agent" and tag in MAIN_AGENT_CALL_TAGS) or (
            stream == "protocol_generation" and tag == "protocol_request_user_prompt"
        ):
            pass
        else:
            continue

        stream_key = str(stream)
        stream_call_index = stream_call_counts.get(stream_key, 0)
        stream_call_counts[stream_key] = stream_call_index + 1

        descriptor = {
            "call_index": len(calls),
            "stream_call_index": stream_call_index,
            "stream": stream,
            "event_index": event.get("event_index"),
            "tag": tag,
            "iteration": event.get("iteration"),
            "agent_number": event.get("agent_number"),
        }

        parsed = event.get("parsed")
        if isinstance(parsed, Mapping):
            if "shell_command" in parsed:
                descriptor["shell_command"] = parsed.get("shell_command")
            if "reasoning" in parsed:
                descriptor["reasoning"] = parsed.get("reasoning")
            if "builder_version" in parsed:
                descriptor["builder_version"] = parsed.get("builder_version")

        calls.append(descriptor)

    return calls


def rebuild_main_agent_call_messages(
    session: Mapping[str, Any],
    *,
    event_index: int,
) -> list[dict[str, Any]]:
    """Rebuild the exact main-agent messages array used for one model call."""
    target_event = _resolve_event(session, event_index=event_index)
    if target_event.get("stream") != "main_agent":
        raise ValueError("Target event is not a main-agent event")
    if target_event.get("tag") not in MAIN_AGENT_CALL_TAGS:
        raise ValueError("Target event is not a replayable main-agent call")

    target_agent_number = target_event.get("agent_number")
    if not isinstance(target_agent_number, int):
        raise ValueError("Main-agent replay event is missing agent_number")

    rebuilt_messages: list[dict[str, Any]] = []
    for event in _get_session_events(session):
        current_event_index = event.get("event_index")
        if not isinstance(current_event_index, int):
            continue
        if current_event_index >= event_index:
            break
        if event.get("stream") != "main_agent":
            continue
        if event.get("agent_number") != target_agent_number:
            continue

        metadata = event.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("included_in_history") is False:
            continue

        message = event.get("message")
        if isinstance(message, Mapping):
            rebuilt_messages.append(_copy_message(message))

    return rebuilt_messages


def rebuild_model_call_messages(
    session: Mapping[str, Any],
    *,
    event_index: int,
) -> list[dict[str, Any]]:
    """Rebuild the exact messages array for a saved OpenRouter call."""
    event = _resolve_event(session, event_index=event_index)
    stream = event.get("stream")
    tag = event.get("tag")

    if stream == "main_agent" and tag in MAIN_AGENT_CALL_TAGS:
        return rebuild_main_agent_call_messages(session, event_index=event_index)
    if stream == "protocol_generation" and tag == "protocol_request_user_prompt":
        return rebuild_protocol_request_messages(session, event)

    raise ValueError(f"Event {event_index} is not a replayable OpenRouter call")
