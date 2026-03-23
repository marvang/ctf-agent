import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import MagicMock, patch

import src.experiment_utils.main_experiment_agent as experiment_agent
import src.utils.workspace as workspace

WORKSPACE_OS: Any = workspace.os  # type: ignore[attr-defined]
WORKSPACE_SHUTIL: Any = workspace.shutil  # type: ignore[attr-defined]
WORKSPACE_SUBPROCESS: Any = workspace.subprocess  # type: ignore[attr-defined]


class WorkspaceCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        workspace._sudo_verified = False

    def test_cleanup_workspace_skips_sudo_when_nothing_needs_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(WORKSPACE_SUBPROCESS, "run") as run_mock:
            result = workspace.cleanup_workspace(
                temp_dir,
                approved_patterns=[],
                files_to_empty=["flags.txt"],
                auto_confirm=True,
            )

        self.assertTrue(result)
        run_mock.assert_not_called()

    def test_cleanup_workspace_uses_unprivileged_delete_when_possible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            with patch.object(WORKSPACE_SUBPROCESS, "run") as run_mock:
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

            self.assertTrue(result)
            run_mock.assert_not_called()
            self.assertFalse(os.path.exists(junk_path))
            self.assertEqual(os.path.getsize(flags_path), 0)

    def test_cleanup_workspace_recreates_root_owned_flags_without_sudo_when_delete_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            real_open = open
            write_attempts = 0

            def fake_open(path: str, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
                nonlocal write_attempts
                if path == flags_path and mode == "w" and write_attempts == 0:
                    write_attempts += 1
                    raise PermissionError("root-owned")
                return real_open(path, mode, *args, **kwargs)

            with (
                patch("builtins.open", side_effect=fake_open),
                patch.object(WORKSPACE_SUBPROCESS, "run") as run_mock,
            ):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

            self.assertTrue(result)
            run_mock.assert_not_called()
            self.assertEqual(os.path.getsize(flags_path), 0)

    def test_cleanup_escalates_to_sudo_on_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            # realpath resolves symlinks (e.g. /var -> /private/var on macOS)
            resolved_junk_path = os.path.realpath(junk_path)
            with open(junk_path, "w") as handle:
                handle.write("junk")

            def fake_run(
                command: list[str],
                capture_output: bool = False,
                text: bool = False,
            ) -> subprocess.CompletedProcess[str]:
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "rm", "-rf", "--", resolved_junk_path]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(f"Unexpected command: {command}")

            with (
                patch.object(WORKSPACE_SHUTIL, "rmtree", side_effect=PermissionError("root-owned")),
                patch.object(WORKSPACE_OS, "remove", side_effect=PermissionError("root-owned")),
                patch.object(WORKSPACE_SUBPROCESS, "run", side_effect=fake_run) as run_mock,
            ):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=[],
                    auto_confirm=True,
                )

            self.assertTrue(result)
            sudo_commands = [call.args[0] for call in run_mock.call_args_list]
            self.assertIn(["sudo", "-n", "rm", "-rf", "--", resolved_junk_path], sudo_commands)

    def test_cleanup_fails_without_tty_when_sudo_cache_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")

            stdout = io.StringIO()
            with (
                patch.object(WORKSPACE_SHUTIL, "rmtree", side_effect=PermissionError("root-owned")),
                patch.object(WORKSPACE_OS, "remove", side_effect=PermissionError("root-owned")),
                patch.object(workspace, "_has_interactive_tty", return_value=False),
                patch.object(
                    WORKSPACE_SUBPROCESS,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        ["sudo", "-n", "true"],
                        1,
                        "",
                        "sudo: a password is required",
                    ),
                ),
                redirect_stdout(stdout),
            ):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=[],
                    auto_confirm=True,
                )

            self.assertFalse(result)
            self.assertIn("Run 'sudo -v' first", stdout.getvalue())

    def test_cleanup_rejects_path_escaping_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            escape_link = os.path.join(temp_dir, "escape")
            os.symlink("/tmp", escape_link)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=[],
                    auto_confirm=True,
                )

            self.assertFalse(result)
            self.assertIn("escapes workspace", stdout.getvalue())


class ExperimentWorkspaceCleanupTests(unittest.TestCase):
    @patch.object(experiment_agent, "connect_to_docker")
    @patch.object(experiment_agent, "cleanup_workspace", return_value=False)
    @patch.object(experiment_agent, "load_workspace_approved_patterns", return_value=[])
    @patch.object(experiment_agent, "load_dotenv")
    def test_run_experiment_aborts_before_docker_when_workspace_cleanup_fails(
        self,
        _load_dotenv_mock: MagicMock,
        _load_patterns_mock: MagicMock,
        _cleanup_mock: MagicMock,
        connect_to_docker_mock: MagicMock,
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
