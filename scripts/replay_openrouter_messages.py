#!/usr/bin/env python3
"""
Rebuild OpenRouter `messages` payloads from a saved session.json file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.replay import list_replayable_model_calls, rebuild_model_call_messages


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Reconstruct OpenRouter messages arrays from session.json",
    )
    parser.add_argument("session_path", help="Path to session.json")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List replayable OpenRouter calls found in the session",
    )
    parser.add_argument(
        "--call-index",
        type=int,
        default=None,
        help="Replay a call by its global call index from --list",
    )
    parser.add_argument(
        "--event-index",
        type=int,
        default=None,
        help="Replay a call by its replay event_index",
    )
    parser.add_argument(
        "--stream",
        choices=["all", "main_agent", "protocol_generation"],
        default="all",
        help="Filter --list output by stream",
    )
    parser.add_argument(
        "--messages-only",
        action="store_true",
        help="Print only the reconstructed messages array",
    )
    return parser.parse_args()


def _load_session(session_path: str) -> dict:
    """Load a saved session JSON file."""
    with open(session_path, encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_event_index(
    calls: list[dict],
    *,
    call_index: int | None,
    event_index: int | None,
) -> int:
    """Resolve a target replay event from the CLI selectors."""
    if call_index is not None and event_index is not None:
        raise ValueError("Choose either --call-index or --event-index, not both")
    if call_index is None and event_index is None:
        raise ValueError("Provide --call-index, --event-index, or --list")

    if event_index is not None:
        return event_index

    for call in calls:
        if call.get("call_index") == call_index:
            resolved = call.get("event_index")
            if isinstance(resolved, int):
                return resolved
            break
    raise ValueError(f"Session does not contain call_index={call_index}")


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    session = _load_session(args.session_path)
    calls = list_replayable_model_calls(session)

    if args.list or (args.call_index is None and args.event_index is None):
        listed_calls = calls
        if args.stream != "all":
            listed_calls = [call for call in calls if call.get("stream") == args.stream]
        print(json.dumps(listed_calls, indent=2))
        return

    event_index = _resolve_event_index(
        calls,
        call_index=args.call_index,
        event_index=args.event_index,
    )
    messages = rebuild_model_call_messages(session, event_index=event_index)

    if args.messages_only:
        print(json.dumps(messages, indent=2))
        return

    selected_call = next(
        (call for call in calls if call.get("event_index") == event_index),
        None,
    )
    payload = {
        "call": selected_call,
        "messages": messages,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
