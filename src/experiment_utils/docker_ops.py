"""Docker container and network lifecycle operations for experiments."""

import re
import subprocess
from pathlib import Path
from typing import Final

from src.config.constants import (
    KALI_CONTAINER_NAME,
    LOCAL_CHALLENGES_COMPOSE_FILE,
    LOCAL_CHALLENGES_NETWORK_NAME,
    get_local_challenge_container_name,
)

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_NETWORK_NAME: Final[str] = LOCAL_CHALLENGES_NETWORK_NAME
_SUBNET: Final[str] = "192.168.0.0/16"
_DEFAULT_KALI_NAME: Final[str] = KALI_CONTAINER_NAME


# ---------------------------------------------------------------------------
# Challenge containers
# ---------------------------------------------------------------------------


def start_container(vm_name: str, compose_file: str | Path = LOCAL_CHALLENGES_COMPOSE_FILE) -> str:
    """Start a fresh local challenge container and return its static IP."""
    compose_path = Path(compose_file)
    container_name = get_local_challenge_container_name(vm_name)

    with compose_path.open() as f:
        content = f.read()

    pattern = rf"^\s*{re.escape(container_name)}:\s*$.*?ipv4_address:\s*(\d+\.\d+\.\d+\.\d+)"
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
    if not match:
        raise ValueError(f"IP not found for {vm_name}")

    ip = match.group(1)

    if not re.search(rf"^\s*{re.escape(container_name)}:\s*$", content, re.MULTILINE):
        raise ValueError(f"Container {container_name} not found in compose file.")

    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_path),
            "up",
            "-d",
            "--force-recreate",
            container_name,
        ],
        check=True,
    )
    return ip


def stop_container(vm_name: str) -> str:
    """Remove a single local challenge container."""
    container_name = get_local_challenge_container_name(vm_name)
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(LOCAL_CHALLENGES_COMPOSE_FILE),
            "rm",
            "-f",
            "-s",
            container_name,
        ],
        check=True,
    )
    return f"{container_name} removed"


# ---------------------------------------------------------------------------
# Kali container
# ---------------------------------------------------------------------------


def start_kali_container(container_name: str = _DEFAULT_KALI_NAME) -> bool:
    """Start Kali Linux container for a fresh environment."""
    try:
        print(f"🔄 Starting {container_name}...")
        subprocess.run(
            ["docker", "compose", "up", "-d", container_name],
            cwd=_PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        print(f"✅ {container_name} started")
        return True
    except subprocess.CalledProcessError as err:
        print(f"❌ Failed to start {container_name}: {err}")
        return False


def stop_kali_container(container_name: str = _DEFAULT_KALI_NAME) -> bool:
    """Force-remove the Kali Linux container if it exists."""
    print(f"🔄 Removing {container_name}...")
    remove = subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True,
        text=True,
    )
    if remove.returncode == 0:
        print(f"✅ {container_name} removed")
        return True

    stderr = (remove.stderr or "").lower()
    if "no such container" in stderr:
        print(f"✅ {container_name} already absent")
        return True

    print(f"❌ Failed to remove {container_name}: {(remove.stderr or '').strip()}")
    return False


# ---------------------------------------------------------------------------
# Docker network
# ---------------------------------------------------------------------------


def start_network(network_name: str = _NETWORK_NAME, subnet: str = _SUBNET) -> None:
    """Create the Docker network if it does not already exist."""
    exists = subprocess.run(
        ["docker", "network", "inspect", network_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if exists.returncode == 0:
        return

    try:
        subprocess.run(
            ["docker", "network", "create", f"--subnet={subnet}", network_name],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as err:
        message = (err.stderr or "").lower()
        if "already exists" in message:
            return
        raise


def stop_network(network_name: str = _NETWORK_NAME) -> None:
    """Remove the Docker network if it exists, force-disconnecting containers if needed."""
    if (
        subprocess.run(
            ["docker", "network", "inspect", network_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        != 0
    ):
        return

    remove = subprocess.run(
        ["docker", "network", "rm", network_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if remove.returncode == 0:
        return

    if remove.stderr and "No such network" in remove.stderr:
        return

    if remove.stderr and ("has active endpoints" in remove.stderr or "in use" in remove.stderr):
        containers = subprocess.run(
            [
                "docker",
                "network",
                "inspect",
                network_name,
                "--format",
                "{{range $id, $_ := .Containers}}{{$id}}\\n{{end}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for container_id in containers:
            if container_id:
                subprocess.run(
                    ["docker", "network", "disconnect", "-f", network_name, container_id],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        subprocess.run(
            ["docker", "network", "rm", network_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    raise RuntimeError(f"Failed to remove network {network_name}: {(remove.stderr or '').strip()}")
