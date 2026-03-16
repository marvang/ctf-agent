"""Git utilities for reproducibility tracking."""

import subprocess


def get_git_commit_hash() -> str | None:
    """Get current git commit hash for reproducibility. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None
