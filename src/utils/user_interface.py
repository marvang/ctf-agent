"""User interface and input utilities. For main.py"""

import re
from pathlib import Path
from typing import Any

from src.config.constants import LOCAL_CHALLENGES_ROOT
from src.utils.environment import EnvironmentType, LocalArch, VpnEnvironment, detect_local_arch

_LOCAL_CTF_ROOT = LOCAL_CHALLENGES_ROOT
_CHALLENGE_PATTERN = re.compile(r"^vm(\d+)$")
_RECOMMENDED_MODELS: list[dict[str, str]] = [
    {
        "name": "minimax/minimax-m2.5",
        "release": "2026-02-12",
        "context": "196,608",
        "input_cost": "$0.25/M input",
        "output_cost": "$1.20/M output",
    },
    {
        "name": "moonshotai/kimi-k2.5",
        "release": "2026-01-27",
        "context": "262,144",
        "input_cost": "$0.45/M input",
        "output_cost": "$2.20/M output",
    },
    {
        "name": "openai/gpt-5.3-codex",
        "release": "2026-02-24",
        "context": "400,000",
        "input_cost": "$1.75/M input",
        "output_cost": "$14/M output",
    },
    {
        "name": "anthropic/claude-opus-4.6",
        "release": "2026-02-04",
        "context": "1,000,000",
        "input_cost": "Starting at $5/M input",
        "output_cost": "Starting at $25/M output",
    },
]


def print_banner() -> None:
    """Display application banner"""
    print("🤖 CTF-AGENT v1.4")
    print("=" * 40)


def discover_local_ctf_challenges(challenges_root: Path = _LOCAL_CTF_ROOT) -> list[str]:
    """Discover local challenge VMs from folder names."""
    if not challenges_root.exists():
        return []

    challenges: list[tuple[int, str]] = []
    for entry in challenges_root.iterdir():
        if not entry.is_dir():
            continue
        match = _CHALLENGE_PATTERN.fullmatch(entry.name)
        if match:
            challenges.append((int(match.group(1)), entry.name))

    challenges.sort(key=lambda item: item[0])
    return [name for _, name in challenges]


def prompt_environment_selection() -> tuple[EnvironmentType, VpnEnvironment | None]:
    """Prompt for execution environment."""
    print("\n🌐 Environment:")
    print("1. Local Docker challenge (default)")
    print("2. Private VPN")
    print("3. HackTheBox")

    choice = input("Choose (1/2/3) [1]: ").strip() or "1"

    if choice == "2":
        return ("private", "private")
    if choice == "3":
        return ("htb", "htb")
    return ("local", None)


def prompt_local_challenge_selection() -> str:
    """Prompt the user to choose a local Docker challenge."""
    challenges = discover_local_ctf_challenges()
    if not challenges:
        print(f"\n❌ No local challenges found in {_LOCAL_CTF_ROOT}")
        return ""

    print("\n🎯 Local Docker Challenge:")
    for index, challenge in enumerate(challenges, start=1):
        print(f"{index}. {challenge}")

    while True:
        raw_choice = input(f"Choose (1-{len(challenges)}) [1]: ").strip() or "1"
        if raw_choice.isdigit():
            selected_index = int(raw_choice)
            if 1 <= selected_index <= len(challenges):
                selected_challenge = challenges[selected_index - 1]
                print(f"✅ Selected local challenge: {selected_challenge}")
                return selected_challenge
        print("⚠️ Invalid challenge selection. Try again.")


def prompt_architecture_selection() -> LocalArch:
    """
    Prompt user to select host architecture.

    Returns:
        Selected local host architecture for prompt rendering.
    """
    detected = detect_local_arch()
    default_choice = "2" if detected == "amd64" else "1"

    print("\n🖥️  Architecture:")
    print("Only changes the LLM system prompt.")
    print("1. aarch64 (Mac - emulated targets)")
    print("2. amd64 (Linux - native targets)")

    arch_choice = input(f"Choose (1/2) [{default_choice}]: ").strip() or default_choice
    local_arch: LocalArch = "amd64" if arch_choice == "2" else "aarch64"

    if local_arch == "amd64":
        print("✅ Using amd64 prompt (native Linux targets)")
    else:
        print("✅ Using aarch64 prompt (emulated targets)")

    return local_arch


def prompt_model_selection(
    default_model: str | None = None,
) -> str:
    """Prompt the user to choose a recommended model or enter a custom one."""
    custom_index = len(_RECOMMENDED_MODELS) + 1
    default_choice = "1"

    if default_model:
        default_match = next(
            (str(index) for index, model in enumerate(_RECOMMENDED_MODELS, start=1) if model["name"] == default_model),
            None,
        )
        default_choice = default_match or str(custom_index)

    print("\n🤖 Model:")
    for index, model in enumerate(_RECOMMENDED_MODELS, start=1):
        print(f"{index}. {model['name']}")
        print(
            f"   Released {model['release']} | {model['context']} context | "
            f"{model['input_cost']} | {model['output_cost']}"
        )
    print(f"{custom_index}. Custom")
    if default_model:
        print(f"Press Enter to keep {default_model}.")

    while True:
        choice = input(f"Choose (1-{custom_index}) [{default_choice}]: ").strip() or default_choice

        if not choice.isdigit():
            print("⚠️ Invalid model selection. Try again.")
            continue

        selected_index = int(choice)
        if 1 <= selected_index <= len(_RECOMMENDED_MODELS):
            selected_model = _RECOMMENDED_MODELS[selected_index - 1]["name"]
            print(f"✅ Using {selected_model}")
            return selected_model

        if selected_index == custom_index:
            prompt = "\nCustom model"
            if default_model:
                prompt += f" [{default_model}]"
            prompt += ": "

            custom_model = input(prompt).strip()
            if custom_model:
                print(f"✅ Using {custom_model}")
                return custom_model
            if default_model:
                print(f"✅ Using {default_model}")
                return default_model
            print("⚠️ Custom model is required. Try again.")
            continue

        print("⚠️ Invalid model selection. Try again.")


def prompt_chap_usage() -> dict[str, Any]:
    """
    Prompt user for CHAP (Context Handoff Protocol) configuration

    Returns:
        Dict with CHAP configuration:
        {
            'enabled': bool,
            'auto_trigger': bool,
            'token_limit_base': int,
            'token_limit_increment': int,
            'min_iterations_for_relay': int
        }
    """
    # Default values
    defaults = {
        "enabled": False,
        "auto_trigger": True,
        "token_limit_base": 100000,
        "token_limit_increment": 5000,
        "min_iterations_for_relay": 35,
    }

    print("\n🔄 Context Handoff (CHAP):")
    print(
        "Enable CHAP: periodic context compaction and relay to fresh instances. This will help manage token limits and maintain performance on longer-running challenges."
    )

    chap_choice = input("Enable CHAP? (y/n) [y]: ").strip().lower()
    enabled = chap_choice == "y" or chap_choice == ""

    if not enabled:
        print("✅ CHAP disabled - running as baseline agent")
        return defaults

    print("✅ CHAP enabled")

    # Auto-trigger configuration
    auto_trigger_choice = input("  Auto-trigger relay on token limit or let agent decide? (y/n) [y]: ").strip().lower()
    auto_trigger = auto_trigger_choice == "y" or auto_trigger_choice == ""

    if auto_trigger:
        print("  ✅ Auto-trigger enabled - both agent and treshold-based relay activated")
    else:
        print("  ✅ Auto-trigger disabled - agent relay only")

    # Token limit base
    token_base_input = input(f"  Token limit? [{defaults['token_limit_base']}]: ").strip()
    try:
        token_limit_base = int(token_base_input) if token_base_input else defaults["token_limit_base"]
    except ValueError:
        print(f"  ⚠️ Invalid value, using default: {defaults['token_limit_base']}")
        token_limit_base = defaults["token_limit_base"]

    token_limit_increment = defaults["token_limit_increment"]
    min_iterations_for_relay = defaults["min_iterations_for_relay"]

    return {
        "enabled": True,
        "auto_trigger": auto_trigger,
        "token_limit_base": token_limit_base,
        "token_limit_increment": token_limit_increment,
        "min_iterations_for_relay": min_iterations_for_relay,
    }


def check_private_vpn_setup() -> bool:
    """Check if .ovpn files exist in the private VPN directory.

    Returns True if at least one .ovpn file is found, False otherwise.
    Prints setup instructions when no files are found.
    """
    vpn_dir = Path(__file__).resolve().parents[2] / "ctf-workspace" / "vpn" / "private"
    ovpn_files = list(vpn_dir.glob("*.ovpn"))
    if ovpn_files:
        return True

    print(f"\n⚠️  No .ovpn file found in {vpn_dir}")
    print("   To set up your private VPN:")
    print(f"   1. Place your .ovpn file in {vpn_dir}")
    print("   2. Add any required cert/key files to the same directory")
    print(f"   3. See {vpn_dir / 'README.md'} for details")
    return False


def prompt_vpn_script_selection(scripts: list[str]) -> str:
    """Prompt user to select a VPN connection script.

    If only one script is found, auto-selects it.
    Returns the selected script filename.
    """
    if len(scripts) == 1:
        print(f"🔗 Using VPN script: {scripts[0]}")
        return scripts[0]

    print("\n🔗 VPN connection scripts found:")
    for i, script in enumerate(scripts, 1):
        print(f"  {i}. {script}")

    while True:
        choice = input(f"Select script (1-{len(scripts)}) [1]: ").strip() or "1"
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(scripts):
                selected = scripts[idx - 1]
                print(f"✅ Using: {selected}")
                return selected
        print("⚠️  Invalid selection. Try again.")


def prompt_target_ip() -> str:
    """
    Prompt user for target identifier with minimal validation

    Returns:
        Target string, or empty string if validation fails
    """
    target_ip = input("\n🎯 Target IP: ").strip()
    if not target_ip:
        print("❌ Target IP is required. Exiting...")
        return ""

    return target_ip


def prompt_custom_instructions() -> str:
    """
    Prompt user for optional custom instructions

    Returns:
        Custom instructions string, or empty string if none provided
    """
    print("\n📝 Initial Instructions:")
    print("=" * 40)
    custom_instructions = input("Add custom instructions? (press Enter to skip): ").strip()

    if custom_instructions:
        print("✅ Custom instructions added")

    return custom_instructions


def print_config_summary(target_info: str) -> None:
    """
    Display configuration summary

    Args:
        target_info: Target description (IP or "Local container")
    """
    print(f"\n⚙️  Target: {target_info}")
    print("=" * 40)
