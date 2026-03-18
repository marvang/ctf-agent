"""Shared workspace paths and cleanup configuration."""

import shutil
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

WORKSPACE_DIR = str(_PROJECT_ROOT / "ctf-workspace")
SESSION_WORKSPACES_ROOT = _PROJECT_ROOT / "ctf-workspaces"
CONTAINER_WORKSPACE_DIR = "/ctf-workspace"
WORKSPACE_FILES_TO_EMPTY = [
    "flags.txt",
    "report.txt",
]
WORKSPACE_APPROVED_PATTERNS = [
    "vpn/**",
    "venv/**",
]


def get_workspace_dir(normalized_id: str | None = None) -> str:
    """Return the host workspace directory for a shared or isolated session. Expects a pre-normalized ID."""
    if normalized_id is None:
        return WORKSPACE_DIR
    return str(SESSION_WORKSPACES_ROOT / normalized_id)


def ensure_workspace_dir(workspace_dir: str) -> str:
    """Create a workspace directory and seed shared VPN material when isolated."""
    workspace_root = Path(workspace_dir)
    workspace_root.mkdir(parents=True, exist_ok=True)

    default_workspace = Path(WORKSPACE_DIR)
    vpn_source = default_workspace / "vpn"
    vpn_target = workspace_root / "vpn"
    if workspace_root != default_workspace and vpn_source.exists() and not vpn_target.exists():
        try:
            vpn_target.symlink_to(vpn_source, target_is_directory=True)
        except OSError:
            shutil.copytree(vpn_source, vpn_target, dirs_exist_ok=True)

    return str(workspace_root)


def read_captured_flag(workspace_dir: str = WORKSPACE_DIR) -> str | None:
    """Read flag from workspace/flags.txt or workspace/flag.txt."""
    workspace_root = Path(workspace_dir)
    for filename in ("flags.txt", "flag.txt"):
        flags_path = workspace_root / filename
        if not flags_path.exists():
            continue
        try:
            content = flags_path.read_text().strip()
        except Exception as exc:
            print(f"⚠️  Error reading flag file {filename}: {exc}")
            return None
        if content:
            return content
    return None


def load_workspace_approved_patterns() -> list[str]:
    """Return workspace preserve rules used during cleanup."""
    return WORKSPACE_APPROVED_PATTERNS.copy()
