"""Docker container and network lifecycle operations for experiments."""

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Final

import yaml

from src.config.constants import (
    KALI_CONTAINER_NAME,
    LOCAL_CHALLENGES_COMPOSE_FILE,
    LOCAL_CHALLENGES_NETWORK_NAME,
    LOCAL_CHALLENGES_SUBNET,
    get_local_challenge_container_name,
)
from src.config.workspace import CONTAINER_WORKSPACE_DIR, ensure_workspace_dir

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_NETWORK_NAME: Final[str] = LOCAL_CHALLENGES_NETWORK_NAME
_SUBNET: Final[str] = LOCAL_CHALLENGES_SUBNET
_DEFAULT_KALI_NAME: Final[str] = KALI_CONTAINER_NAME
_KALI_COMPOSE_FILE: Final[Path] = _PROJECT_ROOT / "docker-compose.yml"


def _load_compose_service(compose_file: str | Path, service_name: str) -> dict[str, Any]:
    """Return the raw compose service definition."""
    compose_path = Path(compose_file)
    with compose_path.open() as handle:
        compose_config = yaml.safe_load(handle) or {}

    services = compose_config.get("services") or {}
    service_config = services.get(service_name)
    if not isinstance(service_config, dict):
        raise ValueError(f"Service {service_name} not found in compose file {compose_path}")
    return service_config


def _remove_container_if_present(container_name: str) -> None:
    """Delete a stale container if it exists."""
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _resolve_volume_mount(mount: str, compose_path: Path, volume_target_overrides: dict[str, str] | None = None) -> str:
    """Resolve a compose volume string into a docker-run mount."""
    parts = mount.split(":")
    if len(parts) < 2:
        return mount

    source = parts[0]
    target = parts[1]
    mode = ":".join(parts[2:]) if len(parts) > 2 else ""

    if volume_target_overrides and target in volume_target_overrides:
        source = volume_target_overrides[target]
    elif source.startswith("."):
        source = str((compose_path.parent / source).resolve())

    resolved = f"{source}:{target}"
    if mode:
        resolved = f"{resolved}:{mode}"
    return resolved


def _iter_environment_flags(environment: Any) -> list[str]:
    """Translate compose environment definitions into docker-run flags."""
    flags: list[str] = []
    if isinstance(environment, dict):
        for key, value in environment.items():
            flags += ["-e", f"{key}={value}"]
    elif isinstance(environment, list):
        for item in environment:
            flags += ["-e", str(item)]
    return flags


def _command_args_from_compose(command: Any) -> list[str]:
    """Return CLI arguments for a compose command override."""
    if command is None:
        return []
    if isinstance(command, list):
        return [str(part) for part in command]
    return shlex.split(str(command))


def _entrypoint_args_from_compose(entrypoint: Any) -> tuple[list[str], list[str]]:
    """Return ``(entrypoint_flags, extra_command_prefix)`` for docker-run.

    ``--entrypoint`` only accepts the executable; remaining list elements
    must be prepended to the container command.
    """
    if entrypoint is None:
        return [], []
    if isinstance(entrypoint, list):
        parts = [str(part) for part in entrypoint]
        return ["--entrypoint", parts[0]], parts[1:]
    return ["--entrypoint", str(entrypoint)], []


def _run_container_from_service(
    service_name: str,
    compose_file: str | Path,
    container_name: str,
    network_name: str,
    *,
    ip_address: str | None = None,
    volume_target_overrides: dict[str, str] | None = None,
    include_host_ports: bool = True,
) -> None:
    """Start a detached container from a compose service definition."""
    compose_path = Path(compose_file)
    service_config = _load_compose_service(compose_path, service_name)

    _remove_container_if_present(container_name)

    cmd: list[str] = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "--network",
        network_name,
    ]
    if ip_address:
        cmd += ["--ip", ip_address]

    platform = service_config.get("platform")
    if platform:
        cmd += ["--platform", str(platform)]
    if service_config.get("init"):
        cmd.append("--init")
    if service_config.get("tty"):
        cmd.append("-t")
    if service_config.get("stdin_open"):
        cmd.append("-i")

    working_dir = service_config.get("working_dir")
    if working_dir:
        cmd += ["-w", str(working_dir)]

    restart = service_config.get("restart")
    if restart:
        cmd += ["--restart", str(restart)]

    cmd += _iter_environment_flags(service_config.get("environment"))

    for cap in service_config.get("cap_drop", []):
        cmd += ["--cap-drop", str(cap)]
    for cap in service_config.get("cap_add", []):
        cmd += ["--cap-add", str(cap)]
    for device in service_config.get("devices", []):
        cmd += ["--device", str(device)]
    for rule in service_config.get("device_cgroup_rules", []):
        cmd += ["--device-cgroup-rule", str(rule)]

    for volume in service_config.get("volumes", []):
        cmd += [
            "-v",
            _resolve_volume_mount(str(volume), compose_path, volume_target_overrides=volume_target_overrides),
        ]

    if include_host_ports:
        for port in service_config.get("ports", []):
            cmd += ["-p", str(port)]

    entrypoint_flags, entrypoint_cmd_prefix = _entrypoint_args_from_compose(service_config.get("entrypoint"))
    cmd += entrypoint_flags

    image = service_config.get("image") or service_name
    cmd.append(str(image))
    cmd.extend(entrypoint_cmd_prefix)
    cmd.extend(_command_args_from_compose(service_config.get("command")))

    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _inspect_container_ip(container_name: str, network_name: str) -> str:
    """Return a container's IP for the given Docker network."""
    inspect = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            f'{{{{(index .NetworkSettings.Networks "{network_name}").IPAddress}}}}',
            container_name,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return inspect.stdout.strip()


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


def start_challenge_container_standalone(
    challenge_name: str,
    container_name: str,
    network_name: str,
    compose_file: str | Path = LOCAL_CHALLENGES_COMPOSE_FILE,
    target_ip: str | None = None,
) -> str:
    """Start a challenge container directly via docker run with compose-derived settings."""
    _run_container_from_service(
        service_name=challenge_name,
        compose_file=compose_file,
        container_name=container_name,
        network_name=network_name,
        ip_address=target_ip,
        include_host_ports=False,
    )

    if target_ip:
        return target_ip
    return _inspect_container_ip(container_name, network_name)


def stop_challenge_container_standalone(container_name: str) -> str:
    """Force-remove a standalone challenge container."""
    _remove_container_if_present(container_name)
    return f"{container_name} removed"


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


def start_kali_container_standalone(
    container_name: str,
    network_name: str,
    workspace_dir: str,
    compose_file: str | Path = _KALI_COMPOSE_FILE,
) -> bool:
    """Start a Kali container directly via docker run with an isolated workspace mount."""
    try:
        ensure_workspace_dir(workspace_dir)
        print(f"🔄 Starting {container_name} (standalone)...")
        _run_container_from_service(
            service_name=KALI_CONTAINER_NAME,
            compose_file=compose_file,
            container_name=container_name,
            network_name=network_name,
            volume_target_overrides={CONTAINER_WORKSPACE_DIR: str(Path(workspace_dir).resolve())},
        )
        print(f"✅ {container_name} started (standalone)")
        return True
    except (subprocess.CalledProcessError, ValueError) as err:
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
