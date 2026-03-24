import unittest

from src.utils.docker_exec import CommandExecutionResult
from src.utils.output import format_command_result_for_llm


class OutputFormattingTests(unittest.TestCase):
    def test_format_command_result_labels_stdout_and_stderr(self) -> None:
        formatted = format_command_result_for_llm(
            CommandExecutionResult(success=False, exit_code=2, stdout="hello", stderr="boom"),
            max_length=100,
        )

        self.assertEqual(formatted.stdout, "hello")
        self.assertEqual(formatted.stderr, "boom")
        self.assertEqual(
            formatted.content,
            "Command executed with exit code 2.\n[STDOUT]\nhello\n[STDERR]\nboom",
        )

    def test_format_command_result_omits_empty_streams(self) -> None:
        formatted = format_command_result_for_llm(
            CommandExecutionResult(success=True, exit_code=0, stdout="", stderr=""),
            max_length=100,
        )

        self.assertEqual(formatted.stdout, "")
        self.assertEqual(formatted.stderr, "")
        self.assertEqual(formatted.content, "Command executed with exit code 0.")

    def test_format_command_result_omits_empty_stderr(self) -> None:
        formatted = format_command_result_for_llm(
            CommandExecutionResult(success=True, exit_code=0, stdout="uid=0", stderr=""),
            max_length=100,
        )

        self.assertEqual(formatted.stdout, "uid=0")
        self.assertEqual(formatted.stderr, "")
        self.assertEqual(
            formatted.content,
            "Command executed with exit code 0.\n[STDOUT]\nuid=0",
        )

    def test_format_command_result_omits_empty_stdout(self) -> None:
        formatted = format_command_result_for_llm(
            CommandExecutionResult(success=False, exit_code=1, stdout="", stderr="permission denied"),
            max_length=100,
        )

        self.assertEqual(formatted.stdout, "")
        self.assertEqual(formatted.stderr, "permission denied")
        self.assertEqual(
            formatted.content,
            "Command executed with exit code 1.\n[STDERR]\npermission denied",
        )

    def test_format_command_result_truncates_each_stream_independently(self) -> None:
        formatted = format_command_result_for_llm(
            CommandExecutionResult(success=False, exit_code=1, stdout="A" * 200, stderr="B" * 200),
            max_length=40,
        )

        self.assertIn("[SYSTEM WARNING: Output truncated.", formatted.stdout)
        self.assertIn("[SYSTEM WARNING: Output truncated.", formatted.stderr)
