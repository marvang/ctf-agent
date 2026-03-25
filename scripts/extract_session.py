#!/usr/bin/env python3
"""Extract a compact representation of session.json for analysis agents.

Strips per-event usage/metadata bloat, keeps commands, output, reasoning,
and key events. Reuses _compact_event() and _is_key_event() from experiment_status.py.

Usage:
    python scripts/extract_session.py <session.json> [--max-output-chars 500] [--max-bytes 300000] [--output /tmp/compact.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Import shared helpers from sibling script
sys.path.insert(0, str(Path(__file__).parent))
from experiment_status import _compact_event, _is_key_event  # type: ignore[import-not-found]


def _extract_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Extract session metadata from context and metrics."""
    context = data.get("context", {})
    metrics = data.get("metrics", {})
    events = data.get("events", [])

    # Find termination tag from last event
    termination_tag = events[-1].get("tag", "unknown") if events else "unknown"

    return {
        "model": data.get("model", context.get("model_name", "unknown")),
        "total_iterations": metrics.get("total_iterations", 0),
        "total_cost": round(metrics.get("total_cost", 0.0), 4),
        "total_time_seconds": round(metrics.get("total_time", 0.0), 1),
        "total_tokens": metrics.get("total_tokens", 0),
        "environment_mode": context.get("environment_mode", "unknown"),
        "target_ip": context.get("target_ip", "unknown"),
        "chap_enabled": data.get("chap_enabled", False),
        "termination_tag": termination_tag,
        "session_id": context.get("session_id", ""),
    }


def _build_key_events(events: list[dict[str, Any]], max_content_len: int) -> list[dict[str, Any]]:
    """Build separate key events array with notes explaining why each is key."""
    key: list[dict[str, Any]] = []
    for event in events:
        if not _is_key_event(event):
            continue
        compact = _compact_event(event, max_content_len)
        tag = event.get("tag", "")
        # Add a note explaining why this is a key event
        if tag in {"assistant_exit", "assistant_relay", "framework_relay_rejection", "framework_empty_retry"}:
            compact["note"] = tag
        elif tag == "framework_command_result":
            parsed = event.get("parsed", {})
            if isinstance(parsed, dict) and parsed.get("exit_code", 0) != 0:
                compact["note"] = f"Non-zero exit ({parsed.get('exit_code')})"
            else:
                compact["note"] = "Contains flag/error pattern"
        elif tag == "assistant_command":
            compact["note"] = "Flag-related command"
        else:
            compact["note"] = "Key event"
        key.append(compact)
    return key


def _truncate_middle(
    compact_events: list[dict[str, Any]], max_bytes: int, full_json: bytes
) -> tuple[list[dict[str, Any]], bool]:
    """If serialized output exceeds max_bytes, keep beginning and end, drop middle."""
    if max_bytes <= 0 or len(full_json) <= max_bytes:
        return compact_events, False

    n = len(compact_events)
    # Keep first 30% and last 30% of events
    head_count = max(5, n * 3 // 10)
    tail_count = max(5, n * 3 // 10)

    if head_count + tail_count >= n:
        return compact_events, False

    dropped = n - head_count - tail_count
    truncated = list(compact_events[:head_count])
    truncated.append({"note": f"--- {dropped} events truncated (middle section) ---"})
    truncated.extend(compact_events[-tail_count:])
    return truncated, True


def extract_session(session_path: str, max_content_len: int = 500, max_bytes: int = 0) -> dict[str, Any]:
    """Extract compact representation from a session.json file."""
    original_bytes = os.path.getsize(session_path)

    with open(session_path) as f:
        data: dict[str, Any] = json.load(f)

    events: list[dict[str, Any]] = data.get("events", [])
    metadata = _extract_metadata(data)

    # Compact all events
    compact_events = [_compact_event(e, max_content_len) for e in events]

    # Truncate system prompt content (agent doesn't need to re-read it)
    for ce in compact_events:
        if ce.get("tag") == "initial_system_prompt" and "content" in ce:
            content = ce["content"]
            if len(content) > 300:
                ce["content"] = content[:300] + "...[system prompt truncated]"

    # Build key events
    key_events = _build_key_events(events, max_content_len)

    # Count iterations (max iteration number across events)
    iterations = max((e.get("iteration", 0) for e in events if "iteration" in e), default=0)

    # Serialize to check size and apply truncation if needed
    full_json = json.dumps(compact_events, indent=1).encode()
    compact_events, was_truncated = _truncate_middle(compact_events, max_bytes, full_json)

    compact_bytes = len(json.dumps(compact_events, indent=1).encode())

    result: dict[str, Any] = {
        "session_metadata": metadata,
        "stats": {
            "original_bytes": original_bytes,
            "compact_bytes": compact_bytes,
            "total_events": len(events),
            "iterations": iterations,
            "key_event_count": len(key_events),
            "truncated": was_truncated,
        },
        "key_events": key_events,
        "compact_events": compact_events,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract compact session representation for analysis agents.")
    parser.add_argument("session_path", help="Path to session.json")
    parser.add_argument("--max-output-chars", type=int, default=500, help="Max chars per command output (default: 500)")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=0,
        help="Max output bytes; truncate middle if exceeded (default: 0 = no limit)",
    )
    parser.add_argument("--output", type=str, default=None, help="Output file path (default: stdout)")
    args = parser.parse_args()

    if not os.path.isfile(args.session_path):
        print(f"Error: file not found: {args.session_path}", file=sys.stderr)
        sys.exit(1)

    result = extract_session(args.session_path, args.max_output_chars, args.max_bytes)
    output_json = json.dumps(result, indent=1)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output_json)
        # Print stats to stderr so caller can see them
        stats = result["stats"]
        print(
            f"Extracted: {stats['original_bytes']} → {stats['compact_bytes']} bytes "
            f"({stats['iterations']} iterations, {stats['key_event_count']} key events"
            f"{', middle truncated' if stats['truncated'] else ''})",
            file=sys.stderr,
        )
    else:
        print(output_json)


if __name__ == "__main__":
    main()
