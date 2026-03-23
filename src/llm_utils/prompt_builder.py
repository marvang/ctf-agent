"""Prompt building utilities for LLM initialization."""

from typing import Any

from src.llm_utils import prompts
from src.utils.environment import EnvironmentType, LocalArch


def build_initial_messages(
    environment_mode: EnvironmentType,
    target_info: str,
    use_chap: bool,
    custom_instructions: str = "",
    agent_ips: dict[str, str] | None = None,
    local_arch: LocalArch | None = None,
) -> list[dict[str, str]]:
    """
    Build initial message list for LLM conversation.

    Args:
        environment_mode: Selected environment mode for the run
        target_info: Target IP address or "Local container"
        use_chap: Whether CHAP protocol should be used
        custom_instructions: Optional custom user instructions
        agent_ips: Dict with agent IP addresses (eth0, tun0 if VPN)

    Returns:
        List of message dictionaries with 'role' and 'content' keys
    """
    system_prompt = prompts.build_system_prompt(
        environment_mode=environment_mode,
        local_arch=local_arch,
        use_chap=use_chap,
    )
    initial_user_prompt = prompts.build_initial_user_prompt(
        environment_mode=environment_mode,
        target_info=target_info,
        use_chap=use_chap,
        custom_instructions=custom_instructions,
        agent_ips=agent_ips,
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_prompt},
    ]


def build_relay_messages(
    session: dict[str, Any],
    environment_mode: EnvironmentType,
    target_info: str,
    custom_instructions: str = "",
    agent_ips: dict[str, str] | None = None,
    local_arch: LocalArch | None = None,
) -> list[dict[str, str]]:
    """
    Build fresh message history with accumulated relay protocols injected.

    Args:
        session: Session object containing relay protocols
        environment_mode: Selected environment mode for the run
        target_info: Target IP address
        custom_instructions: Optional custom user instructions
        agent_ips: Dict with agent IP addresses (eth0, tun0 if VPN)

    Returns:
        Fresh message list with protocols injected into initial user message
    """
    system_prompt = prompts.build_system_prompt(
        environment_mode=environment_mode,
        local_arch=local_arch,
        use_chap=True,
    )
    user_content = prompts.build_relay_user_prompt(
        session=session,
        environment_mode=environment_mode,
        target_info=target_info,
        custom_instructions=custom_instructions,
        agent_ips=agent_ips,
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
