#!/usr/bin/env python3
"""CLI tool for querying experiment status. Outputs JSON for consumption by the live-updates skill."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _file_mtime_iso(path: str) -> str:
    """Return file modification time as ISO-8601 UTC string."""
    mtime = os.path.getmtime(path)
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _load_json(path: str) -> dict[str, Any]:
    with open(path) as f:
        data: dict[str, Any] = json.load(f)
    return data


# ---------------------------------------------------------------------------
# --list
# ---------------------------------------------------------------------------

_TERMINAL_REASONS = {"completed", "interrupted_by_user"}


def _is_running(meta: dict[str, Any]) -> bool:
    """Heuristic: experiment is still running if not terminally stopped and has outstanding challenges."""
    reason = meta.get("termination_reason", "unknown")
    if reason in _TERMINAL_REASONS:
        return False
    if isinstance(reason, str) and reason.startswith("error:"):
        return False
    completed: int = meta.get("completed_challenges", 0)
    total: int = meta.get("challenge_count", 0)
    return completed < total


def cmd_list(results_dir: str, *, running_only: bool = False, limit: int = 0) -> list[dict[str, Any]]:
    """Scan results_dir for experiment_summary.json files and return metadata."""
    experiments: list[dict[str, Any]] = []
    results_path = Path(results_dir)
    if not results_path.is_dir():
        return experiments

    for summary_path in results_path.rglob("experiment_summary.json"):
        try:
            data = _load_json(str(summary_path))
        except (json.JSONDecodeError, OSError):
            continue
        meta = data.get("metadata", {})
        experiment_dir = str(summary_path.parent)

        experiments.append({
            "path": experiment_dir,
            "set_name": meta.get("experiment_set_name", "unknown"),
            "timestamp": meta.get("timestamp", "unknown"),
            "model": meta.get("model", "unknown"),
            "challenge_count": meta.get("challenge_count", 0),
            "completed_challenges": meta.get("completed_challenges", 0),
            "termination_reason": meta.get("termination_reason", "unknown"),
            "chap_enabled": meta.get("chap_enabled", False),
            "test_run": meta.get("test_run", False),
            "parallel_mode": meta.get("parallel_mode", False),
            "running": _is_running(meta),
        })

    experiments.sort(key=lambda e: e["timestamp"], reverse=True)
    if running_only:
        experiments = [e for e in experiments if e["running"]]
    if limit > 0:
        experiments = experiments[:limit]
    return experiments


# ---------------------------------------------------------------------------
# --status
# ---------------------------------------------------------------------------


def cmd_status(experiment_dir: str) -> dict[str, Any]:
    """Per-challenge status for an experiment."""
    summary_path = os.path.join(experiment_dir, "experiment_summary.json")
    if not os.path.isfile(summary_path):
        return {"error": f"No experiment_summary.json in {experiment_dir}"}

    data = _load_json(summary_path)
    meta = data.get("metadata", {})

    # Handle both old (ctf_challenges) and new (challenges) schemas
    challenges: list[str] = meta.get("challenges", meta.get("ctf_challenges", []))

    challenge_statuses: dict[str, dict[str, Any]] = {}
    for challenge in challenges:
        challenge_dir = os.path.join(experiment_dir, challenge)
        summary_file = os.path.join(challenge_dir, "summary.json")
        session_file = os.path.join(challenge_dir, "session.json")

        if os.path.isfile(summary_file):
            try:
                summary = _load_json(summary_file)
            except (json.JSONDecodeError, OSError):
                summary = {}
            challenge_statuses[challenge] = {
                "status": "completed",
                "flag_captured": summary.get("flag_captured"),
                "flag_valid": summary.get("flag_valid"),
                "iterations": summary.get("iterations"),
                "total_cost": summary.get("total_cost"),
                "total_time": summary.get("total_time"),
                "stopping_reason": summary.get("stopping_reason"),
                "error": summary.get("error"),
            }
        elif os.path.isfile(session_file):
            session_data = _load_json(session_file)
            events = session_data.get("events", [])
            metrics = session_data.get("metrics", {})
            challenge_statuses[challenge] = {
                "status": "in_progress",
                "event_count": len(events),
                "iterations": metrics.get("total_iterations", 0),
                "total_cost": metrics.get("total_cost", 0),
                "total_tokens": metrics.get("total_tokens", 0),
                "total_time": metrics.get("total_time", 0),
                "session_file_size": os.path.getsize(session_file),
                "last_modified": _file_mtime_iso(session_file),
            }
        else:
            challenge_statuses[challenge] = {"status": "not_started"}

    return {
        "experiment_path": experiment_dir,
        "metadata": {
            "model": meta.get("model", "unknown"),
            "chap_enabled": meta.get("chap_enabled", False),
            "test_run": meta.get("test_run", False),
            "parallel_mode": meta.get("parallel_mode", False),
            "challenge_count": meta.get("challenge_count", 0),
            "completed_challenges": meta.get("completed_challenges", 0),
            "termination_reason": meta.get("termination_reason", "unknown"),
            "experiment_set_name": meta.get("experiment_set_name", "unknown"),
            "timestamp": meta.get("timestamp", "unknown"),
        },
        "challenges": challenge_statuses,
    }


# ---------------------------------------------------------------------------
# --session-info
# ---------------------------------------------------------------------------


def cmd_session_info(session_path: str) -> dict[str, Any]:
    """Session stats from a session.json file."""
    if not os.path.isfile(session_path):
        return {"error": f"File not found: {session_path}"}

    data = _load_json(session_path)
    events = data.get("events", [])
    metrics = data.get("metrics", {})

    word_count = 0
    for event in events:
        msg = event.get("message", {})
        content = msg.get("content", "")
        if content:
            word_count += len(content.split())

    last_event_index = events[-1]["event_index"] if events else -1

    return {
        "session_path": session_path,
        "event_count": len(events),
        "word_count": word_count,
        "total_tokens": metrics.get("total_tokens", 0) or int(word_count * 1.3),
        "last_event_index": last_event_index,
        "last_modified": _file_mtime_iso(session_path),
        "total_cost": metrics.get("total_cost", 0),
        "total_iterations": metrics.get("total_iterations", 0),
        "total_time": metrics.get("total_time", 0),
    }


# ---------------------------------------------------------------------------
# --extract-key-events
# ---------------------------------------------------------------------------

_HIGH_SIGNAL_TAGS = {
    "assistant_exit",
    "assistant_relay",
    "assistant_auto_relay_discarded",
    "framework_relay_rejection",
    "framework_empty_retry",
    "framework_empty_final_warning",
}

_FLAG_PATTERN = re.compile(r"flag|FLAG|flags\.txt|/ctf-workspace/flags", re.IGNORECASE)
_ERROR_PATTERN = re.compile(r"\berror\b|\bfailed\b|\btimeout\b|\btimed.out\b", re.IGNORECASE)


def _is_key_event(event: dict[str, Any]) -> bool:
    """Check if an event is high-signal."""
    tag = event.get("tag", "")

    if tag in _HIGH_SIGNAL_TAGS:
        return True

    # Non-zero exit code
    if tag == "framework_command_result":
        parsed = event.get("parsed", {})
        if isinstance(parsed, dict) and parsed.get("exit_code", 0) != 0:
            return True

    # Flag-related commands
    if tag == "assistant_command":
        parsed = event.get("parsed", {})
        if isinstance(parsed, dict):
            shell_cmd = parsed.get("shell_command", "")
            reasoning = parsed.get("reasoning", "")
            if _FLAG_PATTERN.search(shell_cmd) or _FLAG_PATTERN.search(reasoning):
                return True

    # Error patterns in message content
    msg = event.get("message", {})
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str) and _ERROR_PATTERN.search(content):
            return True

    return False


def _truncate_event(event: dict[str, Any], max_content_len: int = 500) -> dict[str, Any]:
    """Return a copy of the event with message content truncated."""
    result = dict(event)
    msg = result.get("message")
    if isinstance(msg, dict):
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) > max_content_len:
            result["message"] = {**msg, "content": content[:max_content_len] + "...[truncated]"}
    return result


_ASSISTANT_TAGS = {"assistant_command", "assistant_exit", "assistant_relay"}


def _compact_event(event: dict[str, Any], max_content_len: int = 500) -> dict[str, Any]:
    """Return a minimal representation of an event for analysis agents.

    Strips usage, metadata, stream, model_name, agent_number, timestamps,
    and the full message dict. Keeps only what matters for understanding
    what the agent did and what happened.
    """
    tag = event.get("tag", "")
    compact: dict[str, Any] = {"i": event.get("iteration", event.get("event_index", 0)), "tag": tag}
    parsed = event.get("parsed", {})

    if tag in _ASSISTANT_TAGS:
        if isinstance(parsed, dict):
            reasoning = parsed.get("reasoning", "")
            if reasoning:
                compact["reasoning"] = reasoning
            cmd = parsed.get("shell_command", "")
            if cmd:
                compact["cmd"] = cmd
    elif tag == "framework_command_result":
        compact["tag"] = "cmd_result"
        if isinstance(parsed, dict):
            compact["exit_code"] = parsed.get("exit_code", 0)
        # Use message content as output
        msg = event.get("message", {})
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                compact["output"] = content[:max_content_len] + "...[truncated]" if len(content) > max_content_len else content
    else:
        msg = event.get("message", {})
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                compact["content"] = content[:max_content_len] + "...[truncated]" if len(content) > max_content_len else content

    return compact


def _extract_small(path: str, after_index: int, max_events: int) -> dict[str, Any]:
    """Extract key events via full JSON load."""
    data = _load_json(path)
    events = data.get("events", [])
    total = len(events)

    filtered: list[dict[str, Any]] = []
    context_events: list[dict[str, Any]] = []
    hit_limit = False

    for event in events:
        idx = event.get("event_index", -1)

        # Context: first 3 and last 3 (unless excluded by after_index)
        if after_index < 0 and idx < 3:
            context_events.append(_truncate_event(event))
        if idx >= total - 3 and idx > after_index:
            context_events.append(_truncate_event(event))

        # Skip events before the after_index threshold
        if idx <= after_index:
            continue

        if not hit_limit and _is_key_event(event):
            filtered.append(_truncate_event(event))
            if len(filtered) >= max_events:
                hit_limit = True

    # Merge context events (dedup by event_index)
    seen_indices: set[int] = {e.get("event_index", -1) for e in filtered}
    for ctx in context_events:
        if ctx.get("event_index", -1) not in seen_indices:
            filtered.append(ctx)
            seen_indices.add(ctx.get("event_index", -1))

    filtered.sort(key=lambda e: e.get("event_index", 0))

    return {
        "total_events": total,
        "filtered_events": len(filtered),
        "after_index": after_index,
        "events": filtered,
    }


def cmd_extract_key_events(session_path: str, after_index: int = -1, max_events: int = 50) -> dict[str, Any]:
    """Extract high-signal events from a session."""
    if not os.path.isfile(session_path):
        return {"error": f"File not found: {session_path}"}

    return _extract_small(session_path, after_index, max_events)


# ---------------------------------------------------------------------------
# --extract-recent
# ---------------------------------------------------------------------------


def cmd_extract_recent(session_path: str, tail_iterations: int = 30) -> dict[str, Any]:
    """Extract truncated events from the last N iterations of a session."""
    if not os.path.isfile(session_path):
        return {"error": f"File not found: {session_path}"}

    data = _load_json(session_path)
    events = data.get("events", [])
    metrics = data.get("metrics", {})

    if not events:
        return {
            "session_path": session_path,
            "total_events": 0,
            "total_iterations": 0,
            "tail_from_iteration": 0,
            "cost_so_far": 0,
            "time_so_far": 0,
            "events": [],
        }

    # Find max iteration across events
    max_iter = max((e.get("iteration", 0) for e in events if "iteration" in e), default=0)
    cutoff = max(0, max_iter - tail_iterations + 1)

    # Include events from the tail window, plus non-iteration events at the boundary
    tail_events: list[dict[str, Any]] = []
    for event in events:
        event_iter = event.get("iteration")
        if event_iter is not None and event_iter >= cutoff:
            tail_events.append(_compact_event(event))
        elif event_iter is None and event.get("event_index", 0) >= len(events) - 3:
            # Include trailing non-iteration events (e.g. system messages at end)
            tail_events.append(_compact_event(event))

    return {
        "session_path": session_path,
        "total_events": len(events),
        "total_iterations": max_iter + 1,
        "tail_from_iteration": cutoff,
        "cost_so_far": metrics.get("total_cost", 0),
        "time_so_far": metrics.get("total_time", 0),
        "events": tail_events,
    }


# ---------------------------------------------------------------------------
# --changes-since-last
# ---------------------------------------------------------------------------


def _git(args: list[str]) -> str | None:
    """Run a git command, return stripped stdout or None on failure."""
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _experiment_detail(summary_path: str) -> dict[str, Any]:
    """Extract key fields from an experiment_summary.json for the timeline."""
    try:
        data = _load_json(summary_path)
    except (json.JSONDecodeError, OSError):
        return {}
    meta = data.get("metadata", {})
    return {
        "set_name": meta.get("experiment_set_name", "unknown"),
        "timestamp": meta.get("timestamp", "unknown"),
        "model": meta.get("model", "unknown"),
        "challenge_count": meta.get("challenge_count", 0),
        "chap_enabled": meta.get("chap_enabled", False),
        "test_run": meta.get("test_run", False),
        "purpose": meta.get("purpose"),
        "git_commit_hash": meta.get("git_commit_hash"),
    }


def _commits_between(older_hash: str, newer_hash: str) -> list[dict[str, str]]:
    """Return commits between two hashes (exclusive older, inclusive newer), oldest first."""
    log = _git(["log", "--oneline", "--reverse", f"{older_hash}..{newer_hash}"])
    if not log:
        return []
    return [{"type": "commit", "hash": h, "message": m} for h, m in (line.split(maxsplit=1) for line in log.splitlines())]


_LOCK_EXCLUDES = [":!uv.lock", ":!*.lock", ":!package-lock.json"]
_MAX_RECENT_COMMITS = 50


def _is_lockfile_excluded(path: str) -> bool:
    """Return whether a path should be omitted from change summaries."""
    name = os.path.basename(path)
    return any(fnmatch.fnmatch(name, pattern) for pattern in ("uv.lock", "*.lock", "package-lock.json"))


def _untracked_files() -> list[str]:
    """List untracked files that should be included in change summaries."""
    untracked = _git(["ls-files", "--others", "--exclude-standard"])
    if not untracked:
        return []
    return [path for path in untracked.splitlines() if path and not _is_lockfile_excluded(path)]


def _join_sections(sections: list[str]) -> str:
    """Join non-empty output sections with a blank line."""
    return "\n\n".join(section for section in sections if section)


def cmd_changes_since_last(results_dir: str) -> dict[str, Any]:
    """Build a chronological timeline of up to 3 recent experiments interleaved with commits."""
    # Scan for experiment summaries directly (single parse per file, no cmd_list double-read)
    results_path = Path(results_dir)
    summaries: list[tuple[str, dict[str, Any]]] = []
    if results_path.is_dir():
        for summary_path in results_path.rglob("experiment_summary.json"):
            detail = _experiment_detail(str(summary_path))
            if detail:
                summaries.append((detail.get("timestamp", ""), detail))
    summaries.sort(key=lambda x: x[0], reverse=True)  # newest-first
    detailed = [d for _, d in summaries[:3]]
    detailed.reverse()  # oldest-first for chronological order

    # Build interleaved timeline (all commits + experiments)
    full_timeline: list[dict[str, Any]] = []
    prev_hash: str | None = None
    for exp in detailed:
        cur_hash = exp.get("git_commit_hash")
        if prev_hash and cur_hash and prev_hash != cur_hash:
            full_timeline.extend(_commits_between(prev_hash, cur_hash))
        full_timeline.append({"type": "experiment", **exp})
        if cur_hash:
            prev_hash = cur_hash

    # Split timeline: keep last 20 commits + all experiments in timeline, summarize older commits
    recent: list[dict[str, Any]] = []
    older_messages: list[str] = []
    commit_count = 0
    # Walk backwards to find the 20 most recent commits
    for item in reversed(full_timeline):
        if item["type"] == "commit":
            commit_count += 1
            if commit_count <= _MAX_RECENT_COMMITS:
                recent.append(item)
            else:
                older_messages.append(item["message"])
        else:
            recent.append(item)  # always keep experiments
    recent.reverse()
    older_messages.reverse()

    # Changes since the latest experiment (exclude lockfiles from diffs)
    since_last: dict[str, Any] = {"commits": [], "uncommitted_stat": "", "untracked_files": []}
    latest_hash = detailed[-1].get("git_commit_hash") if detailed else None
    if latest_hash:
        log = _git(["log", "--oneline", "--reverse", f"{latest_hash}..HEAD"])
        since_last["commits"] = log.splitlines() if log else []
    else:
        log = _git(["log", "--oneline", "-10"])
        since_last["commits"] = log.splitlines() if log else []

    tracked_stat = _git(["diff", "--stat", "HEAD", "--", *_LOCK_EXCLUDES]) or ""
    untracked_files = _untracked_files()
    untracked_stat = ""
    if untracked_files:
        untracked_stat = "Untracked files:\n" + "\n".join(untracked_files)

    since_last["uncommitted_stat"] = _join_sections([tracked_stat, untracked_stat])
    since_last["untracked_files"] = untracked_files

    return {
        "timeline": recent,
        "older_commit_count": len(older_messages),
        "older_commit_messages": older_messages,
        "since_last": since_last,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Query experiment status (JSON output)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all experiments with status")
    group.add_argument("--status", metavar="DIR", help="Per-challenge status for an experiment directory")
    group.add_argument("--session-info", metavar="FILE", help="Session stats for a session.json file")
    group.add_argument("--extract-key-events", metavar="FILE", help="Extract high-signal events from session.json")
    group.add_argument("--extract-recent", metavar="FILE", help="Extract last N iterations from session.json")
    group.add_argument(
        "--changes-since-last", action="store_true", help="Timeline of recent experiments + changes since last run"
    )

    parser.add_argument("--results-dir", default="results", help="Results directory (default: results/)")
    parser.add_argument("--running-only", action="store_true", help="Only show running experiments (use with --list)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of results returned (0 = unlimited, use with --list)")
    parser.add_argument("--after-index", type=int, default=-1, help="Only events after this event_index")
    parser.add_argument("--max-events", type=int, default=50, help="Max key events to return (default: 50)")
    parser.add_argument("--tail-iterations", type=int, default=30, help="Number of recent iterations to extract (use with --extract-recent)")

    args = parser.parse_args()

    if args.list:
        result: Any = cmd_list(args.results_dir, running_only=args.running_only, limit=args.limit)
    elif args.status:
        result = cmd_status(args.status)
    elif args.session_info:
        result = cmd_session_info(args.session_info)
    elif args.extract_key_events:
        result = cmd_extract_key_events(args.extract_key_events, args.after_index, args.max_events)
    elif args.extract_recent:
        result = cmd_extract_recent(args.extract_recent, args.tail_iterations)
    elif args.changes_since_last:
        result = cmd_changes_since_last(args.results_dir)
    else:
        parser.print_help()
        sys.exit(1)

    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
