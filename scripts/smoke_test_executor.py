#!/usr/bin/env python3
"""Manual smoke checks for the default non-interactive Docker executor."""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.docker_exec import CommandExecutionResult, execute_command
from src.utils.docker_utils import connect_to_docker


@dataclass(frozen=True)
class SmokeCase:
    """One executor smoke-test case."""

    container_name: str
    label: str
    command: str
    timeout_seconds: int


def _build_cases(exec_container: str, msf_container: str) -> list[SmokeCase]:
    return [
        SmokeCase(exec_container, "stdin_prompt", "python3 -c 'input()'", 10),
        SmokeCase(exec_container, "sudo_no_tty", 'su - tester -c "sudo -k id"', 10),
        SmokeCase(
            exec_container,
            "ssh_password_prompt",
            "ssh tester@127.0.0.1 -o StrictHostKeyChecking=no -o PreferredAuthentications=password -o PubkeyAuthentication=no",
            10,
        ),
        SmokeCase(
            exec_container,
            "tmux_workflow",
            "tmux new-session -d -s smoke 'printf ready; sleep 30' && sleep 1 && tmux capture-pane -p -t smoke",
            10,
        ),
        SmokeCase(exec_container, "curl_version", "curl --version", 10),
        SmokeCase(exec_container, "nmap_version", "nmap --version", 10),
        SmokeCase(exec_container, "grep_passwd", "grep root /etc/passwd", 10),
        SmokeCase(msf_container, "msfconsole_scripted", "msfconsole -q -x 'version; exit -y'", 60),
    ]


def _summarize_stream(text: str, max_chars: int) -> str:
    if not text:
        return "<empty>"
    sanitized = text.replace("\n", "\\n")
    if len(sanitized) <= max_chars:
        return sanitized
    return f"{sanitized[:max_chars]}..."


def _print_result(result: CommandExecutionResult, max_chars: int) -> None:
    print("success:", result.success)
    print("exit_code:", result.exit_code)
    print("timed_out:", result.timed_out)
    print("stdout:", _summarize_stream(result.stdout, max_chars))
    print("stderr:", _summarize_stream(result.stderr, max_chars))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exec-container", default="chap-exec-smoke", help="Container used for general shell checks")
    parser.add_argument("--msf-container", default="chap-msf-smoke", help="Container used for Metasploit checks")
    parser.add_argument("--max-chars", type=int, default=400, help="Maximum characters to print per stream")
    parser.add_argument(
        "--case",
        action="append",
        dest="case_filters",
        help="Optional case label to run. Repeat to run multiple labels.",
    )
    args = parser.parse_args()

    cases = _build_cases(args.exec_container, args.msf_container)
    if args.case_filters:
        requested = set(args.case_filters)
        cases = [case for case in cases if case.label in requested]

    containers: dict[str, object | None] = {}
    for case in cases:
        if case.container_name not in containers:
            _client, container = connect_to_docker(case.container_name)
            containers[case.container_name] = container

        print(f"\n=== {case.label} ===")
        container = containers[case.container_name]
        if container is None:
            print("container missing")
            continue

        result = execute_command(container, case.command, case.timeout_seconds)
        _print_result(result, args.max_chars)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
