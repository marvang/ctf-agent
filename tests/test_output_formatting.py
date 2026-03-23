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

    def test_format_command_result_uses_empty_placeholder(self) -> None:
        formatted = format_command_result_for_llm(
            CommandExecutionResult(success=True, exit_code=0, stdout="", stderr=""),
            max_length=100,
        )

        self.assertIn("[STDOUT]\n<empty>", formatted.content)
        self.assertIn("[STDERR]\n<empty>", formatted.content)

    def test_format_command_result_truncates_each_stream_independently(self) -> None:
        formatted = format_command_result_for_llm(
            CommandExecutionResult(success=False, exit_code=1, stdout="A" * 200, stderr="B" * 200),
            max_length=40,
        )

        self.assertIn("[SYSTEM WARNING: Output truncated.", formatted.stdout)
        self.assertIn("[SYSTEM WARNING: Output truncated.", formatted.stderr)
