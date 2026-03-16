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
