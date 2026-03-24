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
MAX_OUTPUT_LENGTH = 12000
ARTIFACT_SCHEMA_VERSION = 2

# Agent command keywords
EXIT_COMMANDS = ("exit", "quit", "terminate")
RELAY_COMMAND = "relay"

# Local challenges
LOCAL_CHALLENGES_ROOT = _PROJECT_ROOT / "local_challenges" / "autopenbench_improved"
LOCAL_CHALLENGES_ROOT_STR = str(LOCAL_CHALLENGES_ROOT)
LOCAL_CHALLENGES_COMPOSE_FILE = LOCAL_CHALLENGES_ROOT / "docker-compose.yml"
LOCAL_CHALLENGES_NETWORK_NAME = "target_net"
LOCAL_CHALLENGES_SUBNET = "192.168.0.0/16"

_SESSION_SUBNET_SECOND_OCTET_BASE = 200
_SESSION_SUBNET_SECOND_OCTET_SPAN = 50
_SESSION_ID_SANITIZER = re.compile(r"[^a-z0-9_.-]+")
_AUTO_SESSION_SUFFIX_PATTERN = re.compile(r"-(\d+)$")
_SESSION_LABEL_MAX_LENGTH = 18
_SESSION_HASH_LENGTH = 8
_SESSION_SUBNET_CANDIDATE_COUNT = 16


def get_local_challenge_container_name(challenge_name: str) -> str:
    """Return the Docker service/container name for a local challenge VM."""
    return challenge_name


def normalize_session_id(session_id: str) -> str:
    """Return a Docker-safe identifier for session-scoped resources."""
    normalized = _SESSION_ID_SANITIZER.sub("-", session_id.strip().lower()).strip("-.")
    if not normalized:
        raise ValueError("Session ID must contain at least one alphanumeric character")
    return normalized


def _truncate_session_label(normalized_id: str) -> str:
    """Return a readable label that preserves auto-generated numeric suffixes."""
    readable = normalized_id[:_SESSION_LABEL_MAX_LENGTH].rstrip("-.")
    if len(normalized_id) <= _SESSION_LABEL_MAX_LENGTH:
        return readable or "session"

    suffix_match = _AUTO_SESSION_SUFFIX_PATTERN.search(normalized_id)
    if suffix_match is None:
        return readable or "session"

    numeric_suffix = suffix_match.group(0)
    prefix_budget = _SESSION_LABEL_MAX_LENGTH - len(numeric_suffix)
    if prefix_budget > 0:
        prefix = normalized_id[:prefix_budget].rstrip("-.")
        if prefix:
            return f"{prefix}{numeric_suffix}"

    fallback_prefix = "session"[: max(prefix_budget, 0)].rstrip("-.")
    if fallback_prefix:
        return f"{fallback_prefix}{numeric_suffix}"
    return suffix_match.group(1)[-_SESSION_LABEL_MAX_LENGTH:]


def _session_resource_suffix(normalized_id: str, *, use_hash: bool = True) -> str:
    """Build a readable suffix for session-scoped resources.

    Callers can disable hashing for display-oriented helpers, but Docker-facing
    resource names should keep the hash for collision safety.
    """
    readable = _truncate_session_label(normalized_id)
    if not use_hash:
        return readable
    digest = hashlib.sha256(normalized_id.encode("utf-8")).hexdigest()[:_SESSION_HASH_LENGTH]
    return f"{readable}-{digest}"


def get_session_kali_name(normalized_id: str, *, use_hash: bool = True) -> str:
    """Return a session-scoped Kali container name. Expects a pre-normalized ID."""
    return f"{KALI_CONTAINER_NAME}-{_session_resource_suffix(normalized_id, use_hash=use_hash)}"


def get_session_network_name(normalized_id: str, *, use_hash: bool = True) -> str:
    """Return a session-scoped Docker network name. Expects a pre-normalized ID."""
    return f"{LOCAL_CHALLENGES_NETWORK_NAME}_{_session_resource_suffix(normalized_id, use_hash=use_hash)}"


def get_session_challenge_name(challenge_name: str, normalized_id: str, *, use_hash: bool = True) -> str:
    """Return a session-scoped challenge container name. Expects a pre-normalized ID."""
    return f"{challenge_name}-{_session_resource_suffix(normalized_id, use_hash=use_hash)}"


def get_parallel_kali_name(normalized_id: str, challenge_name: str) -> str:
    """Return a per-challenge Kali container name for parallel experiment mode."""
    combined = f"{normalized_id}-{challenge_name}"
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:_SESSION_HASH_LENGTH]
    label = _truncate_session_label(normalized_id)
    return f"{KALI_CONTAINER_NAME}-{label}-{challenge_name}-{digest}"


def get_parallel_network_name(normalized_id: str, challenge_name: str) -> str:
    """Return a per-challenge Docker network name for parallel experiment mode."""
    combined = f"{normalized_id}-{challenge_name}"
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:_SESSION_HASH_LENGTH]
    label = _truncate_session_label(normalized_id)
    return f"{LOCAL_CHALLENGES_NETWORK_NAME}_{label}-{challenge_name}-{digest}"


def get_parallel_subnet_candidates(
    normalized_id: str, challenge_name: str, count: int = _SESSION_SUBNET_CANDIDATE_COUNT
) -> list[str]:
    """Return a stable sequence of candidate /24 subnets for a per-challenge parallel network."""
    combined = f"{normalized_id}-{challenge_name}"
    digest = hashlib.sha256(combined.encode("utf-8")).digest()
    candidates: list[str] = []
    seen: set[str] = set()

    for index in range(count):
        second_octet = _SESSION_SUBNET_SECOND_OCTET_BASE + (
            digest[index % len(digest)] % _SESSION_SUBNET_SECOND_OCTET_SPAN
        )
        third_octet = digest[(index + 1) % len(digest)]
        subnet = f"10.{second_octet}.{third_octet}.0/24"
        if subnet in seen:
            continue
        seen.add(subnet)
        candidates.append(subnet)

    return candidates


def get_session_subnet_candidates(normalized_id: str, count: int = _SESSION_SUBNET_CANDIDATE_COUNT) -> list[str]:
    """Return a stable sequence of candidate /24 subnets for a session."""
    digest = hashlib.sha256(normalized_id.encode("utf-8")).digest()
    candidates: list[str] = []
    seen: set[str] = set()

    for index in range(count):
        second_octet = _SESSION_SUBNET_SECOND_OCTET_BASE + (
            digest[index % len(digest)] % _SESSION_SUBNET_SECOND_OCTET_SPAN
        )
        third_octet = digest[(index + 1) % len(digest)]
        subnet = f"10.{second_octet}.{third_octet}.0/24"
        if subnet in seen:
            continue
        seen.add(subnet)
        candidates.append(subnet)

    return candidates


def get_session_subnet_from_id(normalized_id: str) -> str:
    """Derive a stable non-overlapping /24 subnet for a session. Expects a pre-normalized ID."""
    return get_session_subnet_candidates(normalized_id, count=1)[0]
