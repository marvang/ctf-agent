"""Workspace management utilities for CTF Agent"""

import fnmatch
import os
import shutil


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
        True if cleanup was performed or approved, False if user cancelled
    """
    # Check if workspace exists
    if not os.path.exists(workspace_dir):
        return True  # Nothing to clean, continue

    workspace_items = list(os.scandir(workspace_dir))

    # Filter items to delete (everything not in approved patterns and not in files_to_empty)
    items_to_delete = []
    for entry in workspace_items:
        item = entry.name
        item_path = entry.path

        # Skip files that should be emptied instead of deleted
        if item in files_to_empty:
            continue

        if not _is_approved_path(item, approved_patterns, entry.is_dir(follow_symlinks=False)):
            items_to_delete.append(item_path)

    # Check which files to empty exist and have content
    files_to_empty_list = []
    for filename in files_to_empty:
        file_path = os.path.join(workspace_dir, filename)
        if os.path.exists(file_path):
            # Check if file has content
            if os.path.getsize(file_path) > 0:
                files_to_empty_list.append(filename)

    # Ask user if they want to clean
    if items_to_delete or files_to_empty_list:
        print("\n🧹 Workspace cleanup:")

        if items_to_delete:
            print(f"\n🗑️  Will DELETE {len(items_to_delete)} item(s):")
            for item in items_to_delete[:5]:  # Show first 5
                print(f"   - {os.path.basename(item)}")
            if len(items_to_delete) > 5:
                print(f"   ... and {len(items_to_delete) - 5} more")

        if files_to_empty_list:
            print("\n📝 Will EMPTY (keep file, clear contents):")
            for filename in files_to_empty_list:
                print(f"   - {filename}")

        if auto_confirm:
            wipe_choice = "y"
        else:
            wipe_choice = input("\n🧹 Proceed with cleanup? (y/n) [y]: ").strip().lower()

        if wipe_choice == "" or wipe_choice == "y":
            # Delete unapproved items
            for item_path in items_to_delete:
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        print(f"🗑️  Deleted directory: {os.path.basename(item_path)}")
                    else:
                        os.remove(item_path)
                        print(f"🗑️  Deleted file: {os.path.basename(item_path)}")
                except Exception as e:
                    print(f"⚠️  Could not delete {os.path.basename(item_path)}: {e}")

            # Empty files that have content
            for filename in files_to_empty_list:
                file_path = os.path.join(workspace_dir, filename)
                try:
                    open(file_path, "w").close()
                    print(f"📝 Emptied: {filename}")
                except Exception as e:
                    print(f"⚠️  Could not empty {filename}: {e}")
            return True
        else:
            print("\n🛑 Cleanup cancelled. Exiting...")
            return False

    # Nothing to clean, continue
    return True
