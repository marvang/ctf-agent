"""Workspace management utilities for CTF Agent"""
import os
import shutil
from typing import List


def cleanup_workspace(
    workspace_dir: str,
    approved_files: List[str],
    files_to_empty: List[str]
) -> bool:
    """
    Clean up workspace from previous sessions.

    Args:
        workspace_dir: Path to workspace directory
        approved_files: List of files/patterns to keep (e.g., "*.ovpn", "connect-htb.sh")
        files_to_empty: List of files to empty (not delete)

    Returns:
        True if cleanup was performed or approved, False if user cancelled
    """
    # Check if workspace exists
    if not os.path.exists(workspace_dir):
        return True  # Nothing to clean, continue

    workspace_items = os.listdir(workspace_dir)

    # Filter items to delete (everything not in approved list and not in FILES_TO_EMPTY)
    items_to_delete = []
    for item in workspace_items:
        item_path = os.path.join(workspace_dir, item)

        # Skip files that should be emptied instead of deleted
        if item in files_to_empty:
            continue

        # Check if item matches any approved pattern
        is_approved = False
        for pattern in approved_files:
            if pattern.startswith("*"):
                # Wildcard pattern (e.g., *.ovpn)
                if item.endswith(pattern[1:]):
                    is_approved = True
                    break
            else:
                # Exact match
                if item == pattern:
                    is_approved = True
                    break

        if not is_approved:
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
        print(f"\n🧹 Workspace cleanup:")

        if items_to_delete:
            print(f"\n🗑️  Will DELETE {len(items_to_delete)} item(s):")
            for item in items_to_delete[:5]:  # Show first 5
                print(f"   - {os.path.basename(item)}")
            if len(items_to_delete) > 5:
                print(f"   ... and {len(items_to_delete) - 5} more")

        if files_to_empty_list:
            print(f"\n📝 Will EMPTY (keep file, clear contents):")
            for filename in files_to_empty_list:
                print(f"   - {filename}")

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
                    open(file_path, 'w').close()
                    print(f"📝 Emptied: {filename}")
                except Exception as e:
                    print(f"⚠️  Could not empty {filename}: {e}")
            return True
        else:
            print("\n🛑 Cleanup cancelled. Exiting...")
            return False

    # Nothing to clean, continue
    return True
