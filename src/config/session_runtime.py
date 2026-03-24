"""Session-scoped runtime resource naming."""

import os
import re
from dataclasses import dataclass

from src.config.constants import (
    get_parallel_kali_name,
    get_parallel_network_name,
    get_parallel_subnet_candidates,
    get_session_challenge_name,
    get_session_kali_name,
    get_session_network_name,
    get_session_subnet_candidates,
    get_session_subnet_from_id,
    normalize_session_id,
)
from src.config.workspace import SESSION_WORKSPACES_ROOT, ensure_workspace_dir, get_workspace_dir

_AUTO_SESSION_PATTERN = re.compile(r"-(\d+)$")


@dataclass
class SessionRuntime:
    """Resolved Docker and workspace resources for a run."""

    session_id: str
    kali_container_name: str
    network_name: str
    subnet: str | None
    subnet_candidates: tuple[str, ...]
    workspace_dir: str
    auto_generated: bool

    def challenge_container_name(self, challenge_name: str) -> str:
        """Return the challenge container name for this session."""
        return get_session_challenge_name(challenge_name, self.session_id)

    def parallel_kali_name(self, challenge_name: str) -> str:
        """Return a per-challenge Kali container name for parallel mode."""
        return get_parallel_kali_name(self.session_id, challenge_name)

    def challenge_workspace_dir(self, challenge_name: str) -> str:
        """Return a per-challenge workspace subdirectory for parallel mode."""
        return ensure_workspace_dir(os.path.join(self.workspace_dir, challenge_name))

    def parallel_network_name(self, challenge_name: str) -> str:
        """Return a per-challenge Docker network name for parallel mode."""
        return get_parallel_network_name(self.session_id, challenge_name)

    def parallel_subnet_candidates(self, challenge_name: str) -> tuple[str, ...]:
        """Return subnet candidates for a per-challenge parallel network."""
        return tuple(get_parallel_subnet_candidates(self.session_id, challenge_name))


def _next_session_number(prefix: str) -> int:
    """Scan ``ctf-workspaces/`` for existing ``{prefix}-N/`` dirs and return max(N)+1."""
    if not SESSION_WORKSPACES_ROOT.is_dir():
        return 1
    max_n = 0
    for child in SESSION_WORKSPACES_ROOT.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if not name.startswith(f"{prefix}-"):
            continue
        match = _AUTO_SESSION_PATTERN.search(name)
        if match:
            max_n = max(max_n, int(match.group(1)))
    return max_n + 1


def auto_generate_session_id(prefix: str = "default") -> str:
    """Generate and reserve the next sequential session ID for *prefix* (e.g. ``default-1``)."""
    normalized_prefix = normalize_session_id(prefix)
    SESSION_WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
    n = _next_session_number(normalized_prefix)
    while True:
        session_id = f"{normalized_prefix}-{n}"
        try:
            SESSION_WORKSPACES_ROOT.joinpath(session_id).mkdir(exist_ok=False)
            return session_id
        except FileExistsError:
            n += 1


def resolve_session_runtime(session_id: str | None, *, auto_prefix: str = "default") -> SessionRuntime:
    """Resolve naming and paths for a run. Auto-generates a session ID when *session_id* is ``None``."""
    if session_id is None:
        generated_id = auto_generate_session_id(auto_prefix)
    else:
        generated_id = normalize_session_id(session_id)

    subnet_candidates = tuple(get_session_subnet_candidates(generated_id))
    return SessionRuntime(
        session_id=generated_id,
        kali_container_name=get_session_kali_name(generated_id),
        network_name=get_session_network_name(generated_id),
        subnet=get_session_subnet_from_id(generated_id),
        subnet_candidates=subnet_candidates,
        workspace_dir=get_workspace_dir(generated_id),
        auto_generated=session_id is None,
    )
