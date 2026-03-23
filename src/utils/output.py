"""Output formatting utilities for the CTF agent."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.utils.docker_exec import CommandExecutionResult

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass(frozen=True)
class FormattedCommandOutput:
    """Sanitized command output ready for prompt history and artifacts."""

    stdout: str
    stderr: str
    content: str


def strip_ansi_escape_codes(text: str) -> str:
    """Remove ANSI escape sequences and non-printable control noise."""
    without_ansi = _ANSI_ESCAPE_RE.sub("", text)
    return "".join(char for char in without_ansi if char in "\n\r\t" or 32 <= ord(char) != 127)


def sanitize_command_output(output: str) -> str:
    """Normalize shell output before storing it in prompts or artifacts."""
    return strip_ansi_escape_codes(output).strip()


def truncate_output(output: str, max_length: int) -> str:
    """Truncate command output using a head+tail strategy to fit within a character limit.

    Returns the original output unchanged if it's already within the limit,
    otherwise keeps the first and last portions with a truncation warning.
    """
    if len(output) <= max_length:
        return output

    separator = "\n...\n"
    head_len = max_length // 2
    tail_len = max(max_length - head_len - len(separator), 0)
    truncated = output[:head_len]
    if tail_len:
        truncated += separator + output[-tail_len:]
    warning = (
        f"[SYSTEM WARNING: Output truncated. Showing first {head_len} and last {tail_len} of {len(output)} characters]\n\n"
    )
    return warning + truncated


def print_initial_prompts(messages: list[dict[str, str]]) -> None:
    """Display the system and user prompts used for a run."""
    print(f"\n{'═' * 60}")
    print("SYSTEM PROMPT")
    print(f"{'═' * 60}")
    print(messages[0]["content"])
    print(f"\n{'═' * 60}")
    print("USER PROMPT")
    print(f"{'═' * 60}")
    print(messages[1]["content"])
    print(f"{'═' * 60}\n")


def format_command_result_for_llm(result: CommandExecutionResult, max_length: int) -> FormattedCommandOutput:
    """Format a structured command result for the LLM with labeled stdout/stderr sections."""
    sanitized_stdout = sanitize_command_output(result.stdout)
    sanitized_stderr = sanitize_command_output(result.stderr)

    stdout_budget = max_length if sanitized_stdout and not sanitized_stderr else max(max_length // 2, 1)
    stderr_budget = max_length if sanitized_stderr and not sanitized_stdout else max(max_length - stdout_budget, 1)

    truncated_stdout = truncate_output(sanitized_stdout, stdout_budget) if sanitized_stdout else "<empty>"
    truncated_stderr = truncate_output(sanitized_stderr, stderr_budget) if sanitized_stderr else "<empty>"

    content = (
        f"Command executed with exit code {result.exit_code}.\n"
        f"[STDOUT]\n{truncated_stdout}\n"
        f"[STDERR]\n{truncated_stderr}"
    )
    return FormattedCommandOutput(
        stdout=truncated_stdout,
        stderr=truncated_stderr,
        content=content,
    )
