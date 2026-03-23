"""Docker command execution utilities"""

import shlex
import threading
from dataclasses import dataclass
from typing import Any

import docker
import docker.errors
from docker.models.containers import Container

from src.utils.network_utils import find_vpn_interface, get_interface_ipv4

TIMEOUT_EXIT_CODE = 124


@dataclass(frozen=True)
class CommandExecutionResult:
    """Structured result for a one-shot command execution."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def _decode_exec_stream(stream: bytes | None) -> str:
    """Decode a Docker exec stdout/stderr stream."""
    if stream is None:
        return ""
    return stream.decode("utf-8", errors="replace").strip()


def _decode_demux_output(output: Any) -> tuple[str, str]:
    """Decode Docker exec output from demux mode."""
    if isinstance(output, tuple):
        stdout_bytes, stderr_bytes = output
        return _decode_exec_stream(stdout_bytes), _decode_exec_stream(stderr_bytes)
    return _decode_exec_stream(output), ""


def execute_command(container: Container, shell_command: str, timeout_seconds: int) -> CommandExecutionResult:
    """
    Execute shell command in Docker container

    Args:
        container: Docker container instance
        shell_command: Command to execute
        timeout_seconds: Timeout in seconds

    Returns:
        Structured execution result with separated stdout/stderr streams.
    """
    result: dict[str, Any] = {"exit_code": None, "stdout": "", "stderr": "", "error": None}

    def run_command() -> None:
        try:
            exit_code, output = container.exec_run(
                ["bash", "-lc", shell_command],
                tty=False,
                stdin=False,
                demux=True,
            )
            result["exit_code"] = exit_code
            result["stdout"], result["stderr"] = _decode_demux_output(output)
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
        return CommandExecutionResult(
            success=False,
            exit_code=TIMEOUT_EXIT_CODE,
            stdout="",
            stderr=f"TIMEOUT: Command exceeded {timeout_seconds}s limit. Try a different approach.",
            timed_out=True,
        )

    if result["error"]:
        if isinstance(result["error"], docker.errors.NotFound):
            error_msg = f"❌ Docker container '{container.name}' not found"
            print(error_msg)
            return CommandExecutionResult(success=False, exit_code=-1, stdout="", stderr=error_msg)
        error_msg = f"❌ Error: {result['error']}"
        print(error_msg)
        return CommandExecutionResult(success=False, exit_code=-1, stdout="", stderr=error_msg)

    exit_code = result["exit_code"] if result["exit_code"] is not None else -1
    return CommandExecutionResult(
        success=exit_code == 0,
        exit_code=exit_code,
        stdout=result["stdout"],
        stderr=result["stderr"],
    )


def cleanup_tmux_session(container: Container) -> None:
    """Kill all tmux sessions in the container."""
    try:
        exit_code, _output = container.exec_run(["bash", "-lc", "tmux list-sessions 2>/dev/null"], tty=False)

        if exit_code == 0:
            container.exec_run(["bash", "-lc", "tmux kill-server"], tty=False)
            print("🧹 Cleaned up all tmux sessions")
    except Exception:
        pass


def get_container_ips(container: Container, use_vpn: bool) -> dict[str, str]:
    """Return dict with eth0 (and VPN interface if present) IPs from the container."""
    ips: dict[str, str] = {}

    try:
        eth0_ip = get_interface_ipv4(container, "eth0")
        if eth0_ip:
            ips["eth0"] = eth0_ip

        if use_vpn:
            vpn_iface = find_vpn_interface(container)
            if vpn_iface:
                vpn_ip = get_interface_ipv4(container, vpn_iface)
                if vpn_ip:
                    ips[vpn_iface] = vpn_ip
    except Exception:
        pass

    return ips
