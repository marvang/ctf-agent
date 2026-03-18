"""Unit tests for PtySessionManager (mocked pexpect.spawn)."""

import time
import unittest
from unittest.mock import MagicMock, patch

from src.utils.pty_session import (
    INTERACTIVE_PROMPT_PATTERNS,
    PtySessionManager,
    dispatch_pty_command,
    resolve_pty_fields,
)


class PtySessionManagerInitTests(unittest.TestCase):
    def test_default_parameters(self) -> None:
        mgr = PtySessionManager(container_name="test-kali")
        self.assertEqual(mgr.container_name, "test-kali")
        self.assertEqual(mgr.idle_timeout, 300)
        self.assertEqual(mgr.prompt_idle, 2.0)
        self.assertEqual(mgr.max_session_lifetime, 1800)
        self.assertIsNone(mgr._session)
        self.assertIsNone(mgr._session_start)

    def test_custom_parameters(self) -> None:
        mgr = PtySessionManager(
            container_name="custom",
            idle_timeout=60,
            prompt_idle=1.0,
            max_session_lifetime=600,
        )
        self.assertEqual(mgr.idle_timeout, 60)
        self.assertEqual(mgr.prompt_idle, 1.0)
        self.assertEqual(mgr.max_session_lifetime, 600)


class PtySessionManagerExecCommandTests(unittest.TestCase):
    @patch("src.utils.pty_session.pexpect.spawn")
    def test_exec_command_basic_eof(self, spawn_mock: MagicMock) -> None:
        """Command runs and exits with EOF."""
        mock_child = MagicMock()
        spawn_mock.return_value = mock_child
        mock_child.isalive.return_value = True

        # First expect call: hits EOF (index = len(patterns) = 10)
        eof_idx = len(INTERACTIVE_PROMPT_PATTERNS)
        mock_child.expect.return_value = eof_idx
        mock_child.before = "uid=0(root)"
        mock_child.after = ""
        mock_child.exitstatus = 0
        mock_child.close.return_value = None

        mgr = PtySessionManager(container_name="test-kali")
        output, exited, exit_code = mgr.exec_command("id")

        self.assertTrue(exited)
        self.assertEqual(exit_code, 0)
        self.assertIn("uid=0(root)", output)
        spawn_mock.assert_called_once()

    @patch("src.utils.pty_session.pexpect.spawn")
    def test_exec_command_timeout(self, spawn_mock: MagicMock) -> None:
        """Command hits idle timeout."""
        mock_child = MagicMock()
        spawn_mock.return_value = mock_child
        mock_child.isalive.return_value = True

        # Timeout index
        timeout_idx = len(INTERACTIVE_PROMPT_PATTERNS) + 1
        mock_child.expect.return_value = timeout_idx
        mock_child.before = "partial output..."
        mock_child.after = ""

        mgr = PtySessionManager(container_name="test-kali")
        output, exited, exit_code = mgr.exec_command("sleep 999")

        self.assertFalse(exited)
        self.assertIsNone(exit_code)
        self.assertIn("partial output", output)

    @patch("src.utils.pty_session.pexpect.spawn")
    def test_exec_command_kills_previous_session(self, spawn_mock: MagicMock) -> None:
        """A new exec_command call terminates the previous session."""
        old_child = MagicMock()
        old_child.isalive.return_value = True

        new_child = MagicMock()
        new_child.isalive.return_value = True
        eof_idx = len(INTERACTIVE_PROMPT_PATTERNS)
        new_child.expect.return_value = eof_idx
        new_child.before = "done"
        new_child.after = ""
        new_child.exitstatus = 0
        new_child.close.return_value = None

        # exec_command calls _kill_session (no spawn), then spawns once
        spawn_mock.return_value = new_child

        mgr = PtySessionManager(container_name="test-kali")
        # Set up as if there's a previous session
        mgr._session = old_child
        mgr._session_start = time.time()

        _output, exited, _exit_code = mgr.exec_command("whoami")

        old_child.terminate.assert_called_once_with(force=True)
        self.assertTrue(exited)


class PtySessionManagerWriteStdinTests(unittest.TestCase):
    def test_write_stdin_no_session(self) -> None:
        """Writing stdin when no session is active returns error message."""
        mgr = PtySessionManager(container_name="test-kali")
        output, exited, exit_code = mgr.write_stdin("password123")

        self.assertEqual(output, "No active session to write to.")
        self.assertTrue(exited)
        self.assertIsNone(exit_code)

    @patch("src.utils.pty_session.pexpect.spawn")
    def test_write_stdin_sends_to_session(self, spawn_mock: MagicMock) -> None:
        """Writing stdin sends text to an active session."""
        mock_child = MagicMock()
        mock_child.isalive.return_value = True
        eof_idx = len(INTERACTIVE_PROMPT_PATTERNS)
        mock_child.expect.return_value = eof_idx
        mock_child.before = "Login successful"
        mock_child.after = ""
        mock_child.exitstatus = 0
        mock_child.close.return_value = None

        mgr = PtySessionManager(container_name="test-kali")
        mgr._session = mock_child
        mgr._session_start = time.time()

        output, _exited, _exit_code = mgr.write_stdin("mypassword")

        mock_child.sendline.assert_called_once_with("mypassword")
        self.assertIn("Login successful", output)


class PtySessionManagerCleanupTests(unittest.TestCase):
    def test_cleanup_no_session(self) -> None:
        """Cleanup is safe when there's no active session."""
        mgr = PtySessionManager(container_name="test-kali")
        mgr.cleanup()  # Should not raise

    def test_cleanup_terminates_session(self) -> None:
        """Cleanup terminates active session."""
        mock_child = MagicMock()
        mock_child.isalive.return_value = True

        mgr = PtySessionManager(container_name="test-kali")
        mgr._session = mock_child
        mgr._session_start = time.time()

        mgr.cleanup()

        mock_child.terminate.assert_called_once_with(force=True)
        self.assertIsNone(mgr._session)
        self.assertIsNone(mgr._session_start)


class PtyPromptPatternTests(unittest.TestCase):
    def test_password_pattern_matches(self) -> None:
        patterns = INTERACTIVE_PROMPT_PATTERNS
        test_strings = [
            "Password: ",
            "password:",
            "Password:",
            "Enter passphrase: ",
            "passphrase:",
        ]
        for s in test_strings:
            matched = any(p.search(s) for p in patterns)
            self.assertTrue(matched, f"Pattern should match: {s!r}")

    def test_confirmation_patterns_match(self) -> None:
        patterns = INTERACTIVE_PROMPT_PATTERNS
        test_strings = [
            "Are you sure you want to continue connecting (yes/no)?",
            "[Y/n]",
            "[y/N]",
            "Continue?",
            "(yes/no/[fingerprint])",
            "login: ",
            "Username: ",
        ]
        for s in test_strings:
            matched = any(p.search(s) for p in patterns)
            self.assertTrue(matched, f"Pattern should match: {s!r}")

    def test_non_matching_strings(self) -> None:
        patterns = INTERACTIVE_PROMPT_PATTERNS
        test_strings = [
            "root@kali:~#",
            "Nmap scan report for 10.0.0.1",
            "HTTP/1.1 200 OK",
        ]
        for s in test_strings:
            matched = any(p.search(s) for p in patterns)
            self.assertFalse(matched, f"Pattern should NOT match: {s!r}")


class PtyPromptDetectionTests(unittest.TestCase):
    @patch("src.utils.pty_session.pexpect.spawn")
    def test_interactive_prompt_detected(self, spawn_mock: MagicMock) -> None:
        """When an interactive prompt is detected, output is returned with prompt text."""
        mock_child = MagicMock()
        spawn_mock.return_value = mock_child
        mock_child.isalive.return_value = True

        # First expect: matches password pattern (index 0)
        # Second expect: TIMEOUT (short prompt_idle wait) with index 1 (the second pattern in [EOF, TIMEOUT])
        mock_child.expect.side_effect = [0, 1]
        mock_child.before = "Enter your password\n"
        mock_child.after = "Password: "

        mgr = PtySessionManager(container_name="test-kali")
        output, exited, exit_code = mgr.exec_command("ssh user@target")

        self.assertFalse(exited)
        self.assertIsNone(exit_code)
        self.assertIn("Password:", output)


class ResolvePtyFieldsTests(unittest.TestCase):
    def test_only_shell_command(self) -> None:
        cmd, stdin = resolve_pty_fields("ls -la", "")
        self.assertEqual(cmd, "ls -la")
        self.assertEqual(stdin, "")

    def test_only_stdin_input(self) -> None:
        cmd, stdin = resolve_pty_fields("", "mypassword")
        self.assertEqual(cmd, "")
        self.assertEqual(stdin, "mypassword")

    def test_stdin_is_filler(self) -> None:
        cmd, stdin = resolve_pty_fields("whoami", "none")
        self.assertEqual(cmd, "whoami")
        self.assertEqual(stdin, "")

    def test_shell_is_filler(self) -> None:
        cmd, stdin = resolve_pty_fields("n/a", "mypassword")
        self.assertEqual(cmd, "")
        self.assertEqual(stdin, "mypassword")

    def test_both_real_prefers_shell(self) -> None:
        cmd, stdin = resolve_pty_fields("id", "yes")
        self.assertEqual(cmd, "id")
        self.assertEqual(stdin, "")

    def test_both_empty(self) -> None:
        cmd, stdin = resolve_pty_fields("", "")
        self.assertEqual(cmd, "")
        self.assertEqual(stdin, "")


class DispatchPtyCommandTests(unittest.TestCase):
    def test_dispatch_exec(self) -> None:
        mgr = MagicMock(spec=PtySessionManager)
        mgr.exec_command.return_value = ("output", True, 0)

        result = dispatch_pty_command(mgr, "id", "")
        mgr.exec_command.assert_called_once_with("id")
        self.assertEqual(result, ("output", True, 0))

    def test_dispatch_stdin(self) -> None:
        mgr = MagicMock(spec=PtySessionManager)
        mgr.write_stdin.return_value = ("ok", False, None)

        result = dispatch_pty_command(mgr, "", "password")
        mgr.write_stdin.assert_called_once_with("password")
        self.assertEqual(result, ("ok", False, None))

    def test_dispatch_both_empty(self) -> None:
        mgr = MagicMock(spec=PtySessionManager)
        result = dispatch_pty_command(mgr, "", "")
        self.assertEqual(result, ("", True, None))
        mgr.exec_command.assert_not_called()
        mgr.write_stdin.assert_not_called()


class ResponseSchemaTests(unittest.TestCase):
    def test_pty_schema_has_stdin_input_field(self) -> None:
        from src.llm_utils.response_schema import get_ctf_pty_response_schema

        schema = get_ctf_pty_response_schema()
        props = schema["json_schema"]["schema"]["properties"]
        self.assertIn("stdin_input", props)
        self.assertIn("shell_command", props)
        self.assertIn("reasoning", props)
        self.assertEqual(
            schema["json_schema"]["schema"]["required"],
            ["reasoning", "shell_command", "stdin_input"],
        )

    def test_original_schema_unchanged(self) -> None:
        from src.llm_utils.response_schema import get_ctf_response_schema

        schema = get_ctf_response_schema()
        props = schema["json_schema"]["schema"]["properties"]
        self.assertNotIn("stdin_input", props)
        self.assertEqual(
            schema["json_schema"]["schema"]["required"],
            ["reasoning", "shell_command"],
        )


if __name__ == "__main__":
    unittest.main()
