"""Git utilities for reproducibility tracking."""

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any


def _run_git_command(args: list[str]) -> str | None:
    """Run a git command and return stripped stdout on success."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _run_git_command_bytes(args: list[str]) -> bytes | None:
    """Run a git command and return raw stdout bytes on success."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None
    return result.stdout


def get_git_commit_hash() -> str | None:
    """Get current git commit hash for reproducibility. Returns None if unavailable."""
    return _run_git_command(["rev-parse", "HEAD"])


def get_git_branch_name() -> str | None:
    """Return the current branch name for provenance."""
    return _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])


def is_git_dirty() -> bool | None:
    """Return whether the worktree has tracked or untracked changes."""
    status = _run_git_command(["status", "--short", "--untracked-files=all"])
    if status is None:
        return None
    return bool(status)


def _hash_untracked_file_contents(digest: Any) -> bool:
    """Fold untracked file paths and contents into the provenance fingerprint."""
    repo_root = _run_git_command(["rev-parse", "--show-toplevel"])
    untracked_files = _run_git_command_bytes(["ls-files", "--others", "--exclude-standard", "--full-name", "-z"])
    if repo_root is None or untracked_files is None:
        return False

    root_path = Path(repo_root)
    added = False
    for raw_path in untracked_files.split(b"\0"):
        if not raw_path:
            continue

        digest.update(b"untracked-path\0")
        digest.update(raw_path)
        digest.update(b"\0")

        file_path = root_path / os.fsdecode(raw_path)
        try:
            if file_path.is_symlink():
                content = os.readlink(file_path).encode("utf-8", "surrogateescape")
                digest.update(b"symlink\0")
            else:
                content = file_path.read_bytes()
                digest.update(b"file\0")
        except OSError as exc:
            content = f"<unreadable:{exc}>".encode("utf-8", "surrogateescape")
            digest.update(b"error\0")

        digest.update(hashlib.sha256(content).hexdigest().encode("ascii"))
        digest.update(b"\0")
        added = True

    return added


def get_git_diff_fingerprint(status: str | None = None) -> str | None:
    """Return a stable fingerprint of the current dirty worktree state."""
    if status is None:
        status = _run_git_command(["status", "--short", "--untracked-files=all"])
    diff = _run_git_command(["diff", "--binary", "HEAD"])
    cached_diff = _run_git_command(["diff", "--binary", "--cached"])

    fingerprint = hashlib.sha256()
    has_content = False
    for label, part in (("status", status), ("diff", diff), ("cached_diff", cached_diff)):
        if not part:
            continue
        fingerprint.update(label.encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(part.encode("utf-8"))
        fingerprint.update(b"\0")
        has_content = True

    if _hash_untracked_file_contents(fingerprint):
        has_content = True

    if not has_content:
        return None
    return fingerprint.hexdigest()


def build_git_provenance() -> dict[str, Any]:
    """Build the git provenance block saved into run artifacts."""
    status = _run_git_command(["status", "--short", "--untracked-files=all"])
    dirty = status is not None and bool(status)
    return {
        "git_commit_hash": get_git_commit_hash(),
        "git_branch": get_git_branch_name(),
        "git_dirty": dirty if status is not None else None,
        "git_diff_fingerprint": get_git_diff_fingerprint(status) if dirty else None,
    }
