"""Shared constants for the CTF agent."""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Docker
KALI_CONTAINER_NAME = "ctf-agent-kali"

# Agent loop defaults
MAX_EMPTY_COMMAND_RETRIES = 5
COMMAND_TIMEOUT_SECONDS = 180
MAX_OUTPUT_LENGTH = 6000

# Local challenges
LOCAL_CHALLENGES_ROOT = _PROJECT_ROOT / "local_challenges" / "autopenbench_improved"
LOCAL_CHALLENGES_ROOT_STR = str(LOCAL_CHALLENGES_ROOT)
LOCAL_CHALLENGES_COMPOSE_FILE = LOCAL_CHALLENGES_ROOT / "docker-compose.yml"
LOCAL_CHALLENGES_NETWORK_NAME = "target_net"


def get_local_challenge_container_name(challenge_name: str) -> str:
    """Return the Docker service/container name for a local challenge VM."""
    return challenge_name


def get_session_kali_name(session_id: str) -> str:
    """Return a session-scoped Kali container name."""
    return f"{KALI_CONTAINER_NAME}-{session_id[:8]}"


def get_session_network_name(session_id: str) -> str:
    """Return a session-scoped Docker network name."""
    return f"{LOCAL_CHALLENGES_NETWORK_NAME}_{session_id[:8]}"


def get_session_challenge_name(challenge_name: str, session_id: str) -> str:
    """Return a session-scoped challenge container name."""
    return f"{challenge_name}-{session_id[:8]}"


def get_session_subnet(session_index: int) -> str:
    """Return a unique /24 subnet for parallel sessions.

    Index 0 = 192.168.0.0/24, 1 = 192.168.1.0/24, etc.
    """
    return f"192.168.{session_index}.0/24"


def get_session_subnet_from_id(session_id: str) -> str:
    """Derive a /24 subnet from a hex session ID (first 4 hex chars -> 0..255)."""
    return get_session_subnet(int(session_id[:4], 16) % 256)
