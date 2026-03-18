"""Session-scoped runtime resource naming."""

from dataclasses import dataclass

from src.config.constants import (
    KALI_CONTAINER_NAME,
    LOCAL_CHALLENGES_NETWORK_NAME,
    get_session_challenge_name,
    get_session_kali_name,
    get_session_network_name,
    get_session_subnet_from_id,
    normalize_session_id,
)
from src.config.workspace import WORKSPACE_DIR, get_workspace_dir


@dataclass(frozen=True)
class SessionRuntime:
    """Resolved Docker and workspace resources for a run."""

    session_id: str | None
    isolated: bool
    kali_container_name: str
    network_name: str
    subnet: str | None
    workspace_dir: str

    def challenge_container_name(self, challenge_name: str) -> str:
        """Return the challenge container name for this session."""
        if not self.isolated or self.session_id is None:
            return challenge_name
        return get_session_challenge_name(challenge_name, self.session_id)


def resolve_session_runtime(session_id: str | None) -> SessionRuntime:
    """Resolve naming and paths for a shared or isolated run."""
    if session_id is None:
        return SessionRuntime(
            session_id=None,
            isolated=False,
            kali_container_name=KALI_CONTAINER_NAME,
            network_name=LOCAL_CHALLENGES_NETWORK_NAME,
            subnet=None,
            workspace_dir=WORKSPACE_DIR,
        )

    normalized = normalize_session_id(session_id)
    return SessionRuntime(
        session_id=normalized,
        isolated=True,
        kali_container_name=get_session_kali_name(normalized),
        network_name=get_session_network_name(normalized),
        subnet=get_session_subnet_from_id(normalized),
        workspace_dir=get_workspace_dir(normalized),
    )
