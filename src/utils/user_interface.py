"""User interface and input utilities"""
import re


def print_banner():
    """Display application banner"""
    print("🤖 CTF-AGENT v1.4")
    print("="*40)


def prompt_environment_selection() -> bool:
    """
    Prompt user to select environment

    Returns:
        True if HackTheBox VPN should be used, False for local container
    """
    print("\n🌐 Environment:")
    print("1. Local container")
    print("2. HackTheBox")

    env_choice = input("Choose (1/2) [2]: ").strip() or "2"
    return env_choice in ["2"]


def prompt_mode_selection() -> str:
    """
    Prompt user to select operation mode

    Returns:
        "auto" or "semi-auto"
    """
    print("\n🤖 Mode:")
    print("1. Auto")
    print("2. Semi-Auto")

    mode_choice = input("Choose (1/2) [1]: ").strip() or "1"
    return "semi-auto" if mode_choice == "2" else "auto"


def prompt_target_ip() -> str:
    """
    Prompt user for target IP address with validation

    Returns:
        Validated IP address string, or empty string if validation fails
    """
    target_ip = input("\n🎯 Target IP: ").strip()

    # Simple IP validation: only dots and digits
    if not target_ip:
        print("❌ Target IP is required for HackTheBox environment. Exiting...")
        return ""
    elif not re.match(r'^[\d.]+$', target_ip):
        print("❌ Invalid IP format. IP should only contain digits and dots. Exiting...")
        return ""

    return target_ip


def prompt_custom_instructions() -> str:
    """
    Prompt user for optional custom instructions

    Returns:
        Custom instructions string, or empty string if none provided
    """
    print("\n📝 Initial Instructions:")
    print("="*40)
    custom_instructions = input("Add custom instructions? (press Enter to skip): ").strip()

    if custom_instructions:
        print(f"✅ Custom instructions added")

    return custom_instructions


def prompt_vpn_continue() -> bool:
    """
    Ask user if they want to continue after VPN connection failure

    Returns:
        True if user wants to continue, False otherwise
    """
    continue_choice = input("\n⚠️  VPN failed. Continue? (y/n) [n]: ").strip().lower()
    return continue_choice == "y"


def print_config_summary(target_info: str, mode: str):
    """
    Display configuration summary

    Args:
        target_info: Target description (IP or "Local container")
        mode: Operation mode ("auto" or "semi-auto")
    """
    print(f"\n⚙️  Target: {target_info} | Mode: {mode}")
    print("="*40)
