"""Docker command execution utilities"""
import docker
import docker.errors
from typing import Tuple


def execute_command(
    docker_client,
    container,
    shell_command: str,
    timeout_seconds: int
) -> Tuple[bool, str, int]:
    """
    Execute shell command in Docker container

    Args:
        docker_client: Docker client instance
        container: Docker container instance
        shell_command: Command to execute
        timeout_seconds: Timeout in seconds

    Returns:
        Tuple of (success: bool, output: str, exit_code: int)
    """
    try:
        final_command = f"timeout {timeout_seconds}s {shell_command}"
        exit_code, output = container.exec_run(
            ["bash", "-lc", final_command],
            tty=True,
            stdin=True,
            environment={"TERM": "xterm-256color"}
        )

        text_out = output.decode().strip()
        success = exit_code == 0

        print(f"\n📤 Output:")
        print(text_out)
        if not success:
            print(f"⚠️  Exit code: {exit_code}")

        return success, text_out, exit_code

    except KeyboardInterrupt:
        print("\\n\\n⚠️  Interrupted")
        return False, "Command interrupted by user", -1
    except docker.errors.NotFound:
        error_msg = "❌ Docker container 'kali-linux' not found"
        print(error_msg)
        return False, error_msg, -1
    except Exception as e:
        error_msg = f"❌ Error: {e}"
        print(error_msg)
        return False, error_msg, -1
