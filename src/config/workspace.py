"""Shared workspace paths and cleanup configuration."""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

WORKSPACE_DIR = str(_PROJECT_ROOT / "ctf-workspace")
WORKSPACE_FILES_TO_EMPTY = [
    "flags.txt",
    "report.txt",
]
WORKSPACE_APPROVED_PATTERNS = [
    "vpn/**",
    "venv/**",
]


def read_captured_flag() -> str | None:
    """Read flag from workspace/flags.txt or workspace/flag.txt."""
    workspace_root = Path(WORKSPACE_DIR)
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
