"""Docker command execution utilities"""

from __future__ import annotations

import shlex
import threading
from typing import Any

import docker
import docker.errors
from docker.models.containers import Container

TIMEOUT_EXIT_CODE = 124


def execute_command(container: Container, shell_command: str, timeout_seconds: int) -> tuple[bool, str, int]:
    """
    Execute shell command in Docker container

    Args:
        container: Docker container instance
        shell_command: Command to execute
        timeout_seconds: Timeout in seconds

    Returns:
        Tuple of (success: bool, output: str, exit_code: int)
    """
    result: dict[str, Any] = {"exit_code": None, "output": None, "error": None}

    def run_command() -> None:
        try:
            exit_code, output = container.exec_run(
                ["bash", "-lc", shell_command], tty=True, stdin=True, environment={"TERM": "xterm-256color"}
            )
            result["exit_code"] = exit_code
            result["output"] = output.decode().strip()
        except Exception as e:
            result["error"] = e

    thread = threading.Thread(target=run_command, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Attempt to kill the hung process inside the container
        try:
            container.exec_run(["bash", "-c", "pkill -9 -f " + shlex.quote(shell_command[:50])], tty=False)
        except Exception:
            pass

        print(f"\n⏱️  Command timed out after {timeout_seconds} seconds")
        return (
            False,
            f"TIMEOUT: Command exceeded {timeout_seconds}s limit. Try a different approach.",
            TIMEOUT_EXIT_CODE,
        )

    if result["error"]:
        if isinstance(result["error"], docker.errors.NotFound):
            error_msg = "❌ Docker container 'kali-linux' not found"
            print(error_msg)
            return False, error_msg, -1
        error_msg = f"❌ Error: {result['error']}"
        print(error_msg)
        return False, error_msg, -1

    exit_code = result["exit_code"] if result["exit_code"] is not None else -1
    success = exit_code == 0
    return success, result["output"] or "", exit_code


def cleanup_tmux_session(container: Container) -> None:
    """Kill all tmux sessions in the container."""
    try:
        exit_code, _output = container.exec_run(["bash", "-lc", "tmux list-sessions 2>/dev/null"], tty=True)

        if exit_code == 0:
            container.exec_run(["bash", "-lc", "tmux kill-server"], tty=True)
            print("🧹 Cleaned up all tmux sessions")
    except Exception:
        pass


def get_container_ips(container: Container, use_vpn: bool) -> dict[str, str]:
    """Return dict with eth0 (and tun0 if VPN) IPs from the container."""
    ips = {}

    try:
        exit_code, output = container.exec_run(
            ["bash", "-lc", "ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1"], tty=True
        )
        if exit_code == 0:
            eth0_ip = output.decode().strip()
            if eth0_ip:
                ips["eth0"] = eth0_ip

        if use_vpn:
            exit_code, output = container.exec_run(
                ["bash", "-lc", "ip addr show tun0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1"], tty=True
            )
            if exit_code == 0:
                tun0_ip = output.decode().strip()
                if tun0_ip:
                    ips["tun0"] = tun0_ip
    except Exception:
        pass

    return ips
