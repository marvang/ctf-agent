import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import src.experiment_utils.main_experiment_agent as experiment_agent
import src.utils.workspace as workspace


class WorkspaceCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset sudo verification state between tests
        workspace._sudo_verified = False

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

    def test_cleanup_workspace_uses_unprivileged_delete_when_possible(self) -> None:
        """When files are user-owned, cleanup should NOT invoke sudo at all."""
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            with patch.object(workspace.subprocess, "run") as run_mock:
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

            self.assertTrue(result)
            # sudo should never be called for user-owned files
            run_mock.assert_not_called()
            # Files should actually be cleaned
            self.assertFalse(os.path.exists(junk_path))
            self.assertEqual(os.path.getsize(flags_path), 0)

    def test_cleanup_escalates_to_sudo_on_permission_error(self) -> None:
        """When unprivileged delete fails with PermissionError, escalate to sudo."""
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")

            def fake_run(command, capture_output=False, text=False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "rm", "-rf", "--", junk_path]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(f"Unexpected command: {command}")

            with patch.object(workspace.shutil, "rmtree", side_effect=PermissionError("root-owned")), patch.object(
                workspace.os, "remove", side_effect=PermissionError("root-owned")
            ), patch.object(workspace.subprocess, "run", side_effect=fake_run) as run_mock:
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=[],
                    auto_confirm=True,
                )

            self.assertTrue(result)
            sudo_commands = [call.args[0] for call in run_mock.call_args_list]
            self.assertIn(["sudo", "-n", "rm", "-rf", "--", junk_path], sudo_commands)

    def test_cleanup_escalates_to_sudo_for_empty_file_on_permission_error(self) -> None:
        """When unprivileged file truncation fails, escalate to sudo with portable shell redirect."""
        with tempfile.TemporaryDirectory() as temp_dir:
            flags_path = os.path.join(temp_dir, "flags.txt")
            with open(flags_path, "w") as handle:
                handle.write("FLAG")

            def fake_run(command, capture_output=False, text=False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command[:3] == ["sudo", "-n", "sh"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(f"Unexpected command: {command}")

            builtin_open = open

            def fake_open(path, *args, **kwargs):
                if str(path) == flags_path and args and "w" in args[0]:
                    raise PermissionError("root-owned")
                return builtin_open(path, *args, **kwargs)

            with patch("builtins.open", side_effect=fake_open), patch.object(
                workspace.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=["flags.txt"],
                    auto_confirm=True,
                )

            self.assertTrue(result)
            # Should have used sudo sh -c ': > file' (portable, not truncate)
            sudo_commands = [call.args[0] for call in run_mock.call_args_list]
            sh_commands = [cmd for cmd in sudo_commands if cmd[:3] == ["sudo", "-n", "sh"]]
            self.assertTrue(len(sh_commands) > 0, "Should have used sudo sh for truncation")

    def test_cleanup_prompts_for_sudo_when_cache_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")

            def fake_run(command, capture_output=False, text=False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 1, "", "sudo: a password is required")
                if command == ["sudo", "-v"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "rm", "-rf", "--", junk_path]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                raise AssertionError(f"Unexpected command: {command}")

            with patch.object(workspace.shutil, "rmtree", side_effect=PermissionError("root-owned")), patch.object(
                workspace.os, "remove", side_effect=PermissionError("root-owned")
            ), patch.object(workspace, "_has_interactive_tty", return_value=True), patch.object(
                workspace.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=[],
                    auto_confirm=True,
                )

            self.assertTrue(result)
            sudo_commands = [call.args[0] for call in run_mock.call_args_list]
            self.assertIn(["sudo", "-v"], sudo_commands)

    def test_cleanup_fails_without_tty_when_sudo_cache_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")

            stdout = io.StringIO()
            with patch.object(workspace.shutil, "rmtree", side_effect=PermissionError("root-owned")), patch.object(
                workspace.os, "remove", side_effect=PermissionError("root-owned")
            ), patch.object(workspace, "_has_interactive_tty", return_value=False), patch.object(
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
                    files_to_empty=[],
                    auto_confirm=True,
                )

            self.assertFalse(result)
            self.assertIn("Run 'sudo -v' first", stdout.getvalue())

    def test_cleanup_fails_when_sudo_delete_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            junk_path = os.path.join(temp_dir, "notes.txt")
            with open(junk_path, "w") as handle:
                handle.write("junk")

            def fake_run(command, capture_output=False, text=False):
                if command == ["sudo", "-n", "true"]:
                    return subprocess.CompletedProcess(command, 0, "", "")
                if command == ["sudo", "-n", "rm", "-rf", "--", junk_path]:
                    return subprocess.CompletedProcess(command, 1, "", "permission denied")
                raise AssertionError(f"Unexpected command: {command}")

            with patch.object(workspace.shutil, "rmtree", side_effect=PermissionError("root-owned")), patch.object(
                workspace.os, "remove", side_effect=PermissionError("root-owned")
            ), patch.object(workspace.subprocess, "run", side_effect=fake_run):
                result = workspace.cleanup_workspace(
                    temp_dir,
                    approved_patterns=[],
                    files_to_empty=[],
                    auto_confirm=True,
                )

            self.assertFalse(result)

    def test_cleanup_rejects_path_escaping_workspace(self) -> None:
        """Path containment check prevents symlink escape attacks."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a symlink inside workspace pointing outside
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

    def test_validate_path_containment(self) -> None:
        self.assertTrue(workspace._validate_path_containment("/workspace/foo", "/workspace"))
        self.assertTrue(workspace._validate_path_containment("/workspace/sub/deep", "/workspace"))
        self.assertFalse(workspace._validate_path_containment("/etc/passwd", "/workspace"))
        self.assertFalse(workspace._validate_path_containment("/workspacefoo", "/workspace"))


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
