import io
import os
import subprocess
import tempfile
import unittest
from collections import defaultdict
from contextlib import redirect_stdout
from unittest.mock import patch

import src.experiment_utils.main_experiment_agent as experiment_agent
import src.utils.workspace as workspace


class WorkspaceCleanupTests(unittest.TestCase):
    def test_cleanup_workspace_skips_sudo_when_nothing_needs_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(workspace.subprocess, "run") as run_mock:
            result = workspace.cleanup_workspace(
                temp_dir,
                approved_patterns=[],
                files_to_empty=["flags.txt"],
                auto_confirm=True,
            )

        self.assertTrue(result)
        run_mock.assert_not_called()

    def test_cleanup_workspace_uses_sudo_commands_when_cleanup_needed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            real_getsize = os.path.getsize
            size_calls = defaultdict(int)

            def fake_getsize(path: str) -> int:
                if path == flags_path:
                    size_calls[path] += 1
                    return 4 if size_calls[path] == 1 else 0
                return real_getsize(path)

            def fake_run(command: list[str], capture_output: bool = False, text: bool = False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "rm", "-rf", "--", junk_path]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "truncate", "-s", "0", flags_path]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(f"Unexpected command: {command}")

            with patch.object(workspace.os.path, "getsize", side_effect=fake_getsize), patch.object(
                workspace.subprocess,
                "run",
                side_effect=fake_run,
            ) as run_mock:
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

        self.assertTrue(result)
        self.assertEqual(
            [call.args[0] for call in run_mock.call_args_list],
            [
                ["sudo", "-n", "true"],
                ["sudo", "-n", "rm", "-rf", "--", junk_path],
                ["sudo", "-n", "truncate", "-s", "0", flags_path],
            ],
        )

    def test_cleanup_workspace_prompts_for_sudo_once_when_cache_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            real_getsize = os.path.getsize
            size_calls = defaultdict(int)

            def fake_getsize(path: str) -> int:
                if path == flags_path:
                    size_calls[path] += 1
                    return 4 if size_calls[path] == 1 else 0
                return real_getsize(path)

            def fake_run(command: list[str], capture_output: bool = False, text: bool = False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 1, "", "sudo: a password is required")
                if command == ["sudo", "-v"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "truncate", "-s", "0", flags_path]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(f"Unexpected command: {command}")

            with patch.object(workspace, "_has_interactive_tty", return_value=True), patch.object(
                workspace.os.path,
                "getsize",
                side_effect=fake_getsize,
            ), patch.object(workspace.subprocess, "run", side_effect=fake_run) as run_mock:
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

        self.assertTrue(result)
        self.assertEqual(
            [call.args[0] for call in run_mock.call_args_list],
            [
                ["sudo", "-n", "true"],
                ["sudo", "-v"],
                ["sudo", "-n", "truncate", "-s", "0", flags_path],
            ],
        )

    def test_cleanup_workspace_fails_without_tty_when_sudo_cache_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            stdout = io.StringIO()
            with patch.object(workspace, "_has_interactive_tty", return_value=False), patch.object(
                workspace.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    ["sudo", "-n", "true"],
                    1,
                    "",
                    "sudo: a password is required",
                ),
            ), redirect_stdout(stdout):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

        self.assertFalse(result)
        self.assertIn("Run 'sudo -v' first", stdout.getvalue())

    def test_cleanup_workspace_fails_when_truncate_verification_shows_remaining_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            real_getsize = os.path.getsize
            size_calls = defaultdict(int)

            def fake_getsize(path: str) -> int:
                if path == flags_path:
                    size_calls[path] += 1
                    return 4 if size_calls[path] == 1 else 1
                return real_getsize(path)

            def fake_run(command: list[str], capture_output: bool = False, text: bool = False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "truncate", "-s", "0", flags_path]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(f"Unexpected command: {command}")

            with patch.object(workspace.os.path, "getsize", side_effect=fake_getsize), patch.object(
                workspace.subprocess,
                "run",
                side_effect=fake_run,
            ):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

        self.assertFalse(result)

    def test_cleanup_workspace_fails_when_delete_command_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")

            def fake_run(command: list[str], capture_output: bool = False, text: bool = False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "rm", "-rf", "--", junk_path]:
                    return subprocess.CompletedProcess(command, 1, "", "permission denied")
                raise AssertionError(f"Unexpected command: {command}")

            with patch.object(workspace.subprocess, "run", side_effect=fake_run):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=[],
                    auto_confirm=True,
                )

        self.assertFalse(result)


class ExperimentWorkspaceCleanupTests(unittest.TestCase):
    @patch.object(experiment_agent, "connect_to_docker")
    @patch.object(experiment_agent, "cleanup_workspace", return_value=False)
    @patch.object(experiment_agent, "load_workspace_approved_patterns", return_value=[])
    @patch.object(experiment_agent, "load_dotenv")
    def test_run_experiment_aborts_before_docker_when_workspace_cleanup_fails(
        self,
        _load_dotenv_mock,
        _load_patterns_mock,
        _cleanup_mock,
        connect_to_docker_mock,
    ) -> None:
        result = experiment_agent.run_experiment_agent(
            experiment_id="exp-1",
            experiment_loop_iteration=1,
            total_loop_iterations=1,
            target_ip="127.0.0.1",
            challenge_name="vm0",
            model_name="test-model",
            chap_enabled=False,
            chap_auto_trigger=False,
            max_iterations=1,
            command_timeout_seconds=1,
            max_cost=1.0,
            max_output_length=100,
            chap_token_limit_base=1000,
            chap_token_limit_increment=100,
        )

        connect_to_docker_mock.assert_not_called()
        self.assertEqual(result["stopping_reason"], "workspace_cleanup_failed")
        self.assertEqual(result["error"], "Workspace cleanup failed - aborting to prevent flag contamination")
