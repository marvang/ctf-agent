"""Prompt building utilities for LLM initialization"""
from typing import List, Dict
from src.llm_utils import prompts


def build_initial_messages(
    use_vpn: bool,
    target_info: str,
    custom_instructions: str = ""
) -> List[Dict[str, str]]:
    """
    Build initial message list for LLM conversation

    Args:
        use_vpn: Whether HackTheBox VPN is being used
        target_info: Target IP address or "Local container"
        custom_instructions: Optional custom user instructions

    Returns:
        List of message dictionaries with 'role' and 'content' keys
    """
    # Select appropriate system prompt based on environment
    if use_vpn:
        system_prompt = prompts.HACKTHEBOX_SYSTEM_PROMPT
        environment_context = f"Environment: HackTheBox: VPN Connected. This is the only allowed target, The target ip address is: {target_info} "
    else:
        system_prompt = prompts.MAIN_SYSTEM_PROMPT
        environment_context = f"Environment: {target_info} (Local Mode)\\nThis is a local container environment. Explore files and local services."

    # Build initial user prompt with optional custom instructions
    if custom_instructions:
        initial_user_prompt = f"{environment_context}\\n\\n{prompts.MAIN_INIT_PROMPT}\\n\\nADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM: {custom_instructions}"
    else:
        initial_user_prompt = f"{environment_context}\\n\\n{prompts.MAIN_INIT_PROMPT}"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_prompt}
    ]
