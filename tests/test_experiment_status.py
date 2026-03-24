"""Tests for scripts/experiment_status.py."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from typing import Any

from scripts.experiment_status import (
    cmd_changes_since_last,
    cmd_extract_key_events,
    cmd_extract_recent,
    cmd_list,
    cmd_session_info,
    cmd_status,
)


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _make_experiment_summary(
    challenges: list[str],
    completed: int,
    model: str = "test-model",
    termination_reason: str = "completed",
    set_name: str = "test",
    timestamp: str = "20260324_120000",
) -> dict[str, Any]:
    return {
        "metadata": {
            "challenges": challenges,
            "challenge_count": len(challenges),
            "completed_challenges": completed,
            "model": model,
            "termination_reason": termination_reason,
            "experiment_set_name": set_name,
            "timestamp": timestamp,
            "chap_enabled": False,
            "give_hints": True,
        }
    }


def _make_session(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "id": "test-session",
        "events": events,
        "metrics": {
            "total_cost": 0.05,
            "total_iterations": len(events) // 2,
            "total_time": 120.0,
        },
        "relay_protocols": [],
        "relay_triggers": [],
    }


def _make_event(
    index: int,
    tag: str = "assistant_command",
    shell_command: str = "ls",
    reasoning: str = "checking files",
    exit_code: int | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_index": index,
        "timestamp": "2026-03-24T12:00:00Z",
        "stream": "main_agent",
        "tag": tag,
        "agent_number": 0,
        "model_name": "test-model",
        "iteration": index // 2,
    }
    if tag == "assistant_command":
        event["parsed"] = {"reasoning": reasoning, "shell_command": shell_command}
        event["message"] = {
            "role": "assistant",
            "content": json.dumps({"reasoning": reasoning, "shell_command": shell_command}),
        }
    elif tag == "framework_command_result":
        event["parsed"] = {"exit_code": exit_code or 0, "stdout": content or "", "stderr": ""}
        event["message"] = {"role": "user", "content": content or "command output"}
    elif tag in ("assistant_exit", "assistant_relay"):
        event["message"] = {"role": "assistant", "content": "exit"}
    else:
        event["message"] = {"role": "system", "content": content or ""}
    return event


class TestCmdList(unittest.TestCase):
    def test_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = cmd_list(tmpdir)
            self.assertEqual(result, [])

    def test_nonexistent_dir(self) -> None:
        result = cmd_list("/nonexistent/path")
        self.assertEqual(result, [])

    def test_finds_and_sorts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Older experiment
            exp1 = os.path.join(tmpdir, "set1", "experiment_20260320_100000")
            _write_json(
                os.path.join(exp1, "experiment_summary.json"),
                _make_experiment_summary(["vm0"], 1, timestamp="20260320_100000"),
            )
            # Newer experiment
            exp2 = os.path.join(tmpdir, "set2", "experiment_20260324_120000")
            _write_json(
                os.path.join(exp2, "experiment_summary.json"),
                _make_experiment_summary(["vm0", "vm1"], 2, timestamp="20260324_120000"),
            )

            result = cmd_list(tmpdir)
            self.assertEqual(len(result), 2)
            # Newest first
            self.assertEqual(result[0]["timestamp"], "20260324_120000")
            self.assertEqual(result[1]["timestamp"], "20260320_100000")

    def test_detects_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = os.path.join(tmpdir, "test", "experiment_20260324_120000")
            _write_json(
                os.path.join(exp, "experiment_summary.json"),
                _make_experiment_summary(["vm0", "vm1"], completed=0, termination_reason="unknown"),
            )
            result = cmd_list(tmpdir)
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["running"])

    def test_completed_not_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = os.path.join(tmpdir, "test", "experiment_20260324_120000")
            _write_json(
                os.path.join(exp, "experiment_summary.json"),
                _make_experiment_summary(["vm0"], completed=1, termination_reason="completed"),
            )
            result = cmd_list(tmpdir)
            self.assertFalse(result[0]["running"])

    def test_running_only_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Running experiment
            exp1 = os.path.join(tmpdir, "run", "experiment_20260324_130000")
            _write_json(
                os.path.join(exp1, "experiment_summary.json"),
                _make_experiment_summary(
                    ["vm0", "vm1"], completed=0, termination_reason="in_progress", timestamp="20260324_130000"
                ),
            )
            # Completed experiment
            exp2 = os.path.join(tmpdir, "done", "experiment_20260324_120000")
            _write_json(
                os.path.join(exp2, "experiment_summary.json"),
                _make_experiment_summary(
                    ["vm0"], completed=1, termination_reason="completed", timestamp="20260324_120000"
                ),
            )

            result = cmd_list(tmpdir, running_only=True)
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["running"])
            self.assertEqual(result[0]["timestamp"], "20260324_130000")

    def test_running_only_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = os.path.join(tmpdir, "done", "experiment_20260324_120000")
            _write_json(
                os.path.join(exp, "experiment_summary.json"),
                _make_experiment_summary(["vm0"], completed=1, termination_reason="completed"),
            )
            result = cmd_list(tmpdir, running_only=True)
            self.assertEqual(result, [])

    def test_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            for i, ts in enumerate(["20260320_100000", "20260322_100000", "20260324_100000"]):
                exp = os.path.join(tmpdir, f"set{i}", f"experiment_{ts}")
                _write_json(
                    os.path.join(exp, "experiment_summary.json"),
                    _make_experiment_summary(["vm0"], completed=1, timestamp=ts),
                )
            result = cmd_list(tmpdir, limit=2)
            self.assertEqual(len(result), 2)
            # Newest first
            self.assertEqual(result[0]["timestamp"], "20260324_100000")
            self.assertEqual(result[1]["timestamp"], "20260322_100000")


class TestCmdStatus(unittest.TestCase):
    def test_completed_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = os.path.join(tmpdir, "experiment_1")
            _write_json(
                os.path.join(exp, "experiment_summary.json"),
                _make_experiment_summary(["vm0"], 1),
            )
            _write_json(
                os.path.join(exp, "vm0", "summary.json"),
                {
                    "flag_captured": "FLAG{test}",
                    "flag_valid": True,
                    "iterations": 10,
                    "total_cost": 0.01,
                    "total_time": 60.0,
                    "stopping_reason": "agent_exit",
                    "error": None,
                },
            )
            result = cmd_status(exp)
            self.assertEqual(result["challenges"]["vm0"]["status"], "completed")
            self.assertTrue(result["challenges"]["vm0"]["flag_valid"])

    def test_in_progress_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = os.path.join(tmpdir, "experiment_1")
            _write_json(
                os.path.join(exp, "experiment_summary.json"),
                _make_experiment_summary(["vm0"], 0, termination_reason="unknown"),
            )
            session = _make_session([_make_event(0), _make_event(1)])
            _write_json(os.path.join(exp, "vm0", "session.json"), session)

            result = cmd_status(exp)
            self.assertEqual(result["challenges"]["vm0"]["status"], "in_progress")
            self.assertIn("event_count", result["challenges"]["vm0"])

    def test_not_started_challenge(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            exp = os.path.join(tmpdir, "experiment_1")
            _write_json(
                os.path.join(exp, "experiment_summary.json"),
                _make_experiment_summary(["vm0", "vm1"], 0, termination_reason="unknown"),
            )
            result = cmd_status(exp)
            self.assertEqual(result["challenges"]["vm0"]["status"], "not_started")
            self.assertEqual(result["challenges"]["vm1"]["status"], "not_started")

    def test_missing_summary(self) -> None:
        result = cmd_status("/nonexistent/path")
        self.assertIn("error", result)


class TestCmdSessionInfo(unittest.TestCase):
    def test_basic_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            events = [
                _make_event(0, tag="initial_system_prompt", content="hello world test"),
                _make_event(1, shell_command="nmap -Pn target"),
                _make_event(2, tag="framework_command_result", content="port 80 open"),
            ]
            _write_json(session_path, _make_session(events))

            result = cmd_session_info(session_path)
            self.assertEqual(result["event_count"], 3)
            self.assertEqual(result["last_event_index"], 2)
            self.assertGreater(result["word_count"], 0)
            self.assertGreater(result["total_tokens"], 0)
            self.assertEqual(result["total_cost"], 0.05)

    def test_missing_file(self) -> None:
        result = cmd_session_info("/nonexistent/session.json")
        self.assertIn("error", result)


class TestCmdExtractKeyEvents(unittest.TestCase):
    def test_filters_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            events = [
                _make_event(0, tag="initial_system_prompt", content="system prompt"),
                _make_event(1, shell_command="nmap target"),
                _make_event(2, tag="framework_command_result", exit_code=0, content="ok"),
                _make_event(3, shell_command="exploit target"),
                _make_event(4, tag="framework_command_result", exit_code=1, content="failed"),
                _make_event(5, tag="assistant_exit"),
            ]
            _write_json(session_path, _make_session(events))

            result = cmd_extract_key_events(session_path)
            tags = [e["tag"] for e in result["events"]]
            # Should include: exit code 1 result, assistant_exit, plus context events
            self.assertIn("assistant_exit", tags)
            self.assertIn("framework_command_result", tags)

    def test_after_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            events = [
                _make_event(0, tag="assistant_exit"),
                _make_event(1, tag="assistant_exit"),
                _make_event(2, tag="assistant_exit"),
                _make_event(3, tag="assistant_exit"),
            ]
            _write_json(session_path, _make_session(events))

            result = cmd_extract_key_events(session_path, after_index=1)
            indices = [e["event_index"] for e in result["events"]]
            self.assertEqual(indices, [2, 3])

    def test_flag_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            events = [
                _make_event(0, shell_command="ls /tmp"),
                _make_event(1, shell_command="cat /root/flag.txt", reasoning="reading the flag"),
                _make_event(2, shell_command="echo done"),
            ]
            _write_json(session_path, _make_session(events))

            result = cmd_extract_key_events(session_path)
            shell_cmds = [
                e.get("parsed", {}).get("shell_command", "")
                for e in result["events"]
                if e.get("tag") == "assistant_command"
            ]
            self.assertTrue(any("flag" in cmd for cmd in shell_cmds))

    def test_missing_file(self) -> None:
        result = cmd_extract_key_events("/nonexistent/session.json")
        self.assertIn("error", result)


class TestCmdExtractRecent(unittest.TestCase):
    def test_returns_tail_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            # 10 iterations = 20 events (command + result each)
            events = []
            for i in range(10):
                events.append(_make_event(i * 2, shell_command=f"cmd_{i}", reasoning=f"step {i}"))
                events[-1]["iteration"] = i
                events.append(_make_event(i * 2 + 1, tag="framework_command_result", content=f"output {i}"))
                events[-1]["iteration"] = i
            _write_json(session_path, _make_session(events))

            result = cmd_extract_recent(session_path, tail_iterations=3)
            self.assertEqual(result["total_events"], 20)
            self.assertEqual(result["total_iterations"], 10)
            self.assertEqual(result["tail_from_iteration"], 7)
            # Should only have events from iterations 7, 8, 9 = 6 events
            self.assertEqual(len(result["events"]), 6)
            iterations = {e.get("i") for e in result["events"]}
            self.assertEqual(iterations, {7, 8, 9})
            # Compact format: no verbose fields
            for evt in result["events"]:
                self.assertNotIn("usage", evt)
                self.assertNotIn("message", evt)
                self.assertNotIn("model_name", evt)
                self.assertNotIn("stream", evt)
            # Command events have reasoning + cmd
            cmds = [e for e in result["events"] if e["tag"] == "assistant_command"]
            self.assertTrue(all("reasoning" in e for e in cmds))
            self.assertTrue(all("cmd" in e for e in cmds))
            # Result events have exit_code + output
            results = [e for e in result["events"] if e["tag"] == "cmd_result"]
            self.assertTrue(all("exit_code" in e for e in results))

    def test_short_session_returns_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            events = [
                _make_event(0, shell_command="nmap target"),
                _make_event(1, tag="framework_command_result", content="port 80"),
            ]
            events[0]["iteration"] = 0
            events[1]["iteration"] = 0
            _write_json(session_path, _make_session(events))

            result = cmd_extract_recent(session_path, tail_iterations=30)
            self.assertEqual(result["tail_from_iteration"], 0)
            self.assertEqual(len(result["events"]), 2)

    def test_includes_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            events = [_make_event(0)]
            events[0]["iteration"] = 0
            _write_json(session_path, _make_session(events))

            result = cmd_extract_recent(session_path)
            self.assertIn("cost_so_far", result)
            self.assertIn("time_so_far", result)
            self.assertEqual(result["cost_so_far"], 0.05)

    def test_empty_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = os.path.join(tmpdir, "session.json")
            _write_json(session_path, _make_session([]))

            result = cmd_extract_recent(session_path)
            self.assertEqual(result["total_events"], 0)
            self.assertEqual(result["events"], [])

    def test_missing_file(self) -> None:
        result = cmd_extract_recent("/nonexistent/session.json")
        self.assertIn("error", result)


class TestCmdChangesSinceLast(unittest.TestCase):
    def test_includes_untracked_files_in_stat_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _run_git(["init"], tmpdir)
            _run_git(["config", "user.name", "Test User"], tmpdir)
            _run_git(["config", "user.email", "test@example.com"], tmpdir)

            with open(os.path.join(tmpdir, ".gitignore"), "w") as f:
                f.write("results/\n")
            with open(os.path.join(tmpdir, "tracked.txt"), "w") as f:
                f.write("base\n")

            _run_git(["add", ".gitignore", "tracked.txt"], tmpdir)
            _run_git(["commit", "-m", "initial"], tmpdir)
            head = _run_git(["rev-parse", "HEAD"], tmpdir)

            experiment_dir = os.path.join(tmpdir, "results", "smoke", "experiment_20260324_120000")
            _write_json(
                os.path.join(experiment_dir, "experiment_summary.json"),
                {
                    "metadata": {
                        "experiment_set_name": "smoke",
                        "timestamp": "20260324_120000",
                        "git_commit_hash": head,
                    }
                },
            )

            with open(os.path.join(tmpdir, "new_script.py"), "w") as f:
                f.write("print('hi')\n")
            with open(os.path.join(tmpdir, "uv.lock"), "w") as f:
                f.write("ignored lockfile contents\n")

            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                result = cmd_changes_since_last("results")
            finally:
                os.chdir(old_cwd)

            since_last = result["since_last"]
            self.assertIn("Untracked files:", since_last["uncommitted_stat"])
            self.assertIn("new_script.py", since_last["uncommitted_stat"])
            self.assertNotIn("uv.lock", since_last["uncommitted_stat"])
            self.assertNotIn("full_diff", since_last)
            self.assertEqual(since_last["untracked_files"], ["new_script.py"])


if __name__ == "__main__":
    unittest.main()
