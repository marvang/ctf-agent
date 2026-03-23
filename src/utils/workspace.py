"""Workspace management utilities for CTF Agent"""

import fnmatch
import os
import shutil
import subprocess
import sys

_CLEANUP_ABORT_MESSAGE = "   Aborting to prevent workspace contamination between runs."

_sudo_verified = False


def _is_approved_path(relative_path: str, approved_patterns: list[str], is_dir: bool) -> bool:
    """Check whether a workspace-relative path matches an approved pattern."""
    normalized_path = relative_path.replace(os.sep, "/")

    for pattern in approved_patterns:
        normalized_pattern = pattern.strip().replace(os.sep, "/")
        if not normalized_pattern:
            continue

        if normalized_pattern.endswith("/**"):
            prefix = normalized_pattern[:-3].rstrip("/")
            if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
                return True

        if is_dir and normalized_pattern.endswith("/"):
            prefix = normalized_pattern.rstrip("/")
            if normalized_path == prefix or normalized_path.startswith(f"{prefix}/"):
                return True

        if fnmatch.fnmatch(normalized_path, normalized_pattern):
            return True

    return False


def _validate_path_containment(item_path: str, workspace_dir: str) -> bool:
    """Ensure item_path is actually inside workspace_dir (prevents symlink escapes)."""
    real_workspace = os.path.realpath(workspace_dir)
    real_item = os.path.realpath(item_path)
    return real_item.startswith(real_workspace + os.sep) or real_item == real_workspace


def _has_interactive_tty() -> bool:
    """Return whether cleanup can safely prompt for sudo credentials."""
    return sys.stdin is not None and sys.stdin.isatty()


def _run_sudo_command(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a non-interactive sudo command used for workspace cleanup."""
    try:
        return subprocess.run(["sudo", "-n", *command], capture_output=True, text=True)
    except OSError as exc:
        print(f"❌ Failed to run sudo command: {exc}")
        return None


def _format_sudo_error(result: subprocess.CompletedProcess[str] | None) -> str:
    """Extract an error message from a sudo command result."""
    if result is None:
        return "failed to invoke sudo"
    return (result.stderr or "").strip() or "unknown error"


def _ensure_sudo_ready() -> bool:
    """Ensure sudo credentials are available before mutating the shared workspace."""
    global _sudo_verified
    if _sudo_verified:
        return True

    try:
        sudo_check = subprocess.run(["sudo", "-n", "true"], capture_output=True, text=True)
    except OSError as exc:
        print(f"❌ Workspace cleanup requires sudo, but invoking sudo failed: {exc}")
        return False

    if sudo_check.returncode == 0:
        _sudo_verified = True
        return True

    if not _has_interactive_tty():
        stderr = (sudo_check.stderr or "").strip()
        print(
            "❌ Workspace cleanup requires sudo to handle Docker-owned files, but no interactive terminal is available."
        )
        if stderr:
            print(f"   sudo error: {stderr}")
        print("   Run 'sudo -v' first, then rerun the agent.")
        return False

    print("\n🔐 Workspace cleanup needs sudo to handle Docker-owned files.")
    try:
        sudo_verify = subprocess.run(["sudo", "-v"])
    except OSError as exc:
        print(f"❌ Sudo verification failed: {exc}")
        return False

    if sudo_verify.returncode == 0:
        _sudo_verified = True
        return True

    print("❌ Sudo verification failed. Aborting workspace cleanup.")
    print("   Run 'sudo -v' first, then rerun the agent.")
    return False


def _delete_workspace_item(item_path: str, workspace_dir: str) -> bool:
    """Delete a workspace path. Tries unprivileged first, escalates to sudo on PermissionError."""
    item_name = os.path.basename(item_path)
    item_type = "directory" if os.path.isdir(item_path) else "file"

    if not _validate_path_containment(item_path, workspace_dir):
        print(f"❌ FATAL: Refusing to delete {item_name}: path escapes workspace directory")
        return False

    try:
        if os.path.islink(item_path):
            os.unlink(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)
        print(f"🗑️  Deleted {item_type}: {item_name}")
        return True
    except PermissionError:
        pass
    except OSError as exc:
        print(f"⚠️  Unprivileged delete failed for {item_name}: {exc}")

    if not _ensure_sudo_ready():
        print(f"❌ FATAL: Could not delete {item_name}: permission denied and sudo not available")
        return False

    resolved_path = os.path.realpath(item_path)
    if not _validate_path_containment(resolved_path, workspace_dir):
        print(f"❌ FATAL: Refusing to delete {item_name}: path escapes workspace directory")
        return False
    result = _run_sudo_command(["rm", "-rf", "--", resolved_path])
    if result is None or result.returncode != 0:
        print(f"❌ FATAL: Could not delete {item_name}: {_format_sudo_error(result)}")
        return False

    print(f"🗑️  Deleted {item_type} (sudo): {item_name}")
    return True


def _empty_workspace_file(file_path: str, workspace_dir: str) -> bool:
    """Empty a workspace file. Tries unprivileged first, escalates to sudo on PermissionError."""
    filename = os.path.basename(file_path)

    if not _validate_path_containment(file_path, workspace_dir):
        print(f"❌ FATAL: Refusing to empty {filename}: path escapes workspace directory")
        return False

    try:
        with open(file_path, "w") as handle:
            handle.truncate(0)
        print(f"📝 Emptied: {filename}")
        return True
    except PermissionError:
        pass
    except OSError as exc:
        print(f"⚠️  Unprivileged truncate failed for {filename}: {exc}")

    try:
        os.remove(file_path)
        with open(file_path, "w"):
            pass
        print(f"📝 Emptied (delete/recreate): {filename}")
        return True
    except PermissionError:
        pass
    except OSError as exc:
        print(f"⚠️  Unprivileged delete-and-recreate failed for {filename}: {exc}")

    if not _ensure_sudo_ready():
        print(f"❌ FATAL: Could not empty {filename}: permission denied and sudo not available")
        return False

    resolved_path = os.path.realpath(file_path)
    if not _validate_path_containment(resolved_path, workspace_dir):
        print(f"❌ FATAL: Refusing to empty {filename}: path escapes workspace directory")
        return False
    result = _run_sudo_command(["sh", "-c", ': > "$1"', "_", resolved_path])
    if result is None or result.returncode != 0:
        print(f"❌ FATAL: Could not empty {filename}: {_format_sudo_error(result)}")
        return False

    print(f"📝 Emptied (sudo): {filename}")
    return True


def cleanup_workspace(
    workspace_dir: str, approved_patterns: list[str], files_to_empty: list[str], auto_confirm: bool = False
) -> bool:
    """
    Clean up workspace from previous sessions.

    Args:
        workspace_dir: Path to workspace directory
        approved_patterns: Workspace-relative keep rules (supports globs and dir/**)
        files_to_empty: List of files to empty (not delete)
        auto_confirm: Skip user confirmation and proceed with cleanup (for automated runs)

    Returns:
        True if cleanup completed or there was nothing to clean, False if cancelled or cleanup failed
    """
    if not os.path.exists(workspace_dir):
        return True

    workspace_items = list(os.scandir(workspace_dir))

    items_to_delete = []
    for entry in workspace_items:
        item = entry.name
        item_path = entry.path

        if item in files_to_empty:
            continue

        if not _is_approved_path(item, approved_patterns, entry.is_dir(follow_symlinks=False)):
            items_to_delete.append(item_path)

    files_to_empty_list = []
    for filename in files_to_empty:
        file_path = os.path.join(workspace_dir, filename)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            files_to_empty_list.append(filename)

    if items_to_delete or files_to_empty_list:
        print("\n🧹 Workspace cleanup:")

        if items_to_delete:
            print(f"\n🗑️  Will DELETE {len(items_to_delete)} item(s):")
            for item in items_to_delete[:5]:
                print(f"   - {os.path.basename(item)}")
            if len(items_to_delete) > 5:
                print(f"   ... and {len(items_to_delete) - 5} more")

        if files_to_empty_list:
            print("\n📝 Will EMPTY (keep file, clear contents):")
            for filename in files_to_empty_list:
                print(f"   - {filename}")

        wipe_choice = "y" if auto_confirm else input("\n🧹 Proceed with cleanup? (y/n) [y]: ").strip().lower()

        if wipe_choice == "" or wipe_choice == "y":
            for item_path in items_to_delete:
                if not _delete_workspace_item(item_path, workspace_dir):
                    print(_CLEANUP_ABORT_MESSAGE)
                    return False

            for filename in files_to_empty_list:
                file_path = os.path.join(workspace_dir, filename)
                if not _empty_workspace_file(file_path, workspace_dir):
                    print(_CLEANUP_ABORT_MESSAGE)
                    return False
            return True

        print("\n🛑 Cleanup cancelled. Exiting...")
        return False

    return True
