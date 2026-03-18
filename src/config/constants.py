"""Shared constants for the CTF agent."""

import hashlib
import re
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
LOCAL_CHALLENGES_SUBNET = "192.168.0.0/16"

_SESSION_SUBNET_SECOND_OCTET_BASE = 200
_SESSION_SUBNET_SECOND_OCTET_SPAN = 50
_SESSION_ID_SANITIZER = re.compile(r"[^a-z0-9_.-]+")


def get_local_challenge_container_name(challenge_name: str) -> str:
    """Return the Docker service/container name for a local challenge VM."""
    return challenge_name


def normalize_session_id(session_id: str) -> str:
    """Return a Docker-safe identifier for session-scoped resources."""
    normalized = _SESSION_ID_SANITIZER.sub("-", session_id.strip().lower()).strip("-.")
    if not normalized:
        raise ValueError("Session ID must contain at least one alphanumeric character")
    return normalized


def get_session_kali_name(normalized_id: str) -> str:
    """Return a session-scoped Kali container name. Expects a pre-normalized ID."""
    return f"{KALI_CONTAINER_NAME}-{normalized_id[:12]}"


def get_session_network_name(normalized_id: str) -> str:
    """Return a session-scoped Docker network name. Expects a pre-normalized ID."""
    return f"{LOCAL_CHALLENGES_NETWORK_NAME}_{normalized_id[:12]}"


def get_session_challenge_name(challenge_name: str, normalized_id: str) -> str:
    """Return a session-scoped challenge container name. Expects a pre-normalized ID."""
    return f"{challenge_name}-{normalized_id[:12]}"


def get_session_subnet_from_id(normalized_id: str) -> str:
    """Derive a stable non-overlapping /24 subnet for a session. Expects a pre-normalized ID."""
    digest = hashlib.sha256(normalized_id.encode("utf-8")).digest()
    second_octet = _SESSION_SUBNET_SECOND_OCTET_BASE + (digest[0] % _SESSION_SUBNET_SECOND_OCTET_SPAN)
    third_octet = digest[1]
    return f"10.{second_octet}.{third_octet}.0/24"
