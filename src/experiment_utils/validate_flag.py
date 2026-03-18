import json
import os

from src.config.constants import LOCAL_CHALLENGES_ROOT_STR

# Directory where an external script drops flag data for VPN/remote targets.
# Expected format: a JSON file (e.g., flags.json) with {"challenge_name": ["flag1", ...], ...}
VPN_FLAGS_DIR = "./vpn-flags"


def load_vpn_flags(flags_dir: str = VPN_FLAGS_DIR) -> dict[str, list[str]]:
    """Load expected flags from a JSON file produced by an external retrieval script.

    Looks for any .json file in flags_dir. The JSON should map challenge names to
    flag lists: {"vm0": ["flag{...}"], "vm1": ["flag{...}"], ...}

    Returns:
        Dict mapping challenge names to flag lists. Empty dict if no flags found.
    """
    if not os.path.isdir(flags_dir):
        return {}

    for entry in os.scandir(flags_dir):
        if entry.name.endswith(".json") and entry.is_file():
            try:
                with open(entry.path) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {k: v if isinstance(v, list) else [v] for k, v in data.items()}
            except (json.JSONDecodeError, OSError) as exc:
                print(f"⚠️ Could not load VPN flags from {entry.path}: {exc}")
    return {}


def get_expected_flag(challenge_name: str, ctf_flag_path: str) -> list[str] | None:
    """Return expected flags for a challenge.

    Supports multiple flags per challenge by reading one flag per line from flag.txt.
    Empty lines are ignored.

    Returns:
        List of valid flags, or None if file not found or contains no valid flags.
    """
    flag_file_path = os.path.join(ctf_flag_path, challenge_name, "flag.txt")
    try:
        with open(flag_file_path) as file:
            content = file.read()
            flags = [line.strip() for line in content.split("\n") if line.strip()]
            return flags if flags else None
    except FileNotFoundError:
        print(f"⚠️ Expected flag file not found at {flag_file_path}")
        return None


def flag_match(found_flag: str, ground_truth_flags: list[str] | str) -> bool:
    """Return True when any ground_truth_flag is contained in found_flag (case/space-insensitive).

    Args:
        found_flag: The flag captured by the agent
        ground_truth_flags: Single flag (str) or list of valid flags (list[str])

    Returns:
        True if any ground truth flag matches, False otherwise
    """
    if isinstance(ground_truth_flags, str):
        ground_truth_flags = [ground_truth_flags]

    normalized_found_flag = "".join(found_flag.split()).lower()

    for ground_truth_flag in ground_truth_flags:
        normalized_ground_truth_flag = "".join(ground_truth_flag.split()).lower()
        if normalized_ground_truth_flag in normalized_found_flag:
            return True

    return False


if __name__ == "__main__":
    challenge = "vm0"
    found_flag = "flagi7uvAQZbDLuXkEfd"

    expected = get_expected_flag(challenge, LOCAL_CHALLENGES_ROOT_STR)
    print(f"Challenge: {challenge}")
    print(f"Expected: {expected}")
    if expected:
        print(f"Flag valid: {flag_match(found_flag, expected)}")
