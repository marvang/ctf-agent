"""
Discord Integration - Relay Messages
Handles relay handoff notifications (auto and manual).
"""

import discord
from typing import Dict, Any
from .core import _safe_send, _create_embed


def send_auto_relay_message(channel_id, relay_data: Dict[str, Any]) -> bool:
    """
    Send auto-relay notification (triggered by automated relay logic).

    Args:
        channel_id: Discord channel ID
        relay_data: Relay data dict with keys:
            - agent_number: Current agent number (int)
            - iteration: Current iteration (int)
            - challenge: Challenge name (optional)
            - experiment_id: Experiment ID (optional)

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_auto_relay_message(
        ...     channel_id="123456789",
        ...     relay_data={
        ...         "agent_number": 2,
        ...         "iteration": 15,
        ...         "challenge": "vm0"
        ...     }
        ... )
    """
    if not channel_id:
        return False

    # Extract relay data
    agent_number = relay_data.get("agent_number", 0)
    iteration = relay_data.get("iteration", 0)
    challenge = relay_data.get("challenge", "Unknown")
    experiment_id = relay_data.get("experiment_id", "")

    # Build fields
    fields = [
        {"name": "Current Agent", "value": f"#{agent_number}", "inline": True},
        {"name": "Next Agent", "value": f"#{agent_number + 1}", "inline": True},
        {"name": "Iteration", "value": str(iteration), "inline": True}
    ]

    if challenge:
        fields.insert(0, {"name": "Challenge", "value": challenge, "inline": True})

    if experiment_id:
        fields.insert(0, {"name": "Experiment", "value": experiment_id, "inline": True})

    # Create embed
    embed = _create_embed(
        title=f"🔄 Auto-Relay: Agent #{agent_number} → Agent #{agent_number + 1}",
        description="Agent context relayed to a fresh instance",
        color=discord.Color.blue(),
        fields=fields
    )

    return _safe_send(channel_id, embed=embed)


def send_manual_relay_message(channel_id, relay_data: Dict[str, Any]) -> bool:
    """
    Send manual relay notification (triggered by agent command).

    Args:
        channel_id: Discord channel ID
        relay_data: Relay data dict with keys:
            - agent_number: Current agent number (int)
            - iteration: Current iteration (int)
            - challenge: Challenge name (optional)
            - experiment_id: Experiment ID (optional)
            - reason: Reason for relay (string, optional)

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_manual_relay_message(
        ...     channel_id="123456789",
        ...     relay_data={
        ...         "agent_number": 1,
        ...         "iteration": 8,
        ...         "challenge": "vm0",
        ...         "reason": "Agent requested context refresh"
        ...     }
        ... )
    """
    if not channel_id:
        return False

    # Extract relay data
    agent_number = relay_data.get("agent_number", 0)
    iteration = relay_data.get("iteration", 0)
    challenge = relay_data.get("challenge", "Unknown")
    experiment_id = relay_data.get("experiment_id", "")
    reason = relay_data.get("reason", "Agent command")

    # Build fields
    fields = [
        {"name": "Reason", "value": f"🤖 {reason}", "inline": True},
        {"name": "Current Agent", "value": f"#{agent_number}", "inline": True},
        {"name": "Next Agent", "value": f"#{agent_number + 1}", "inline": True},
        {"name": "Iteration", "value": str(iteration), "inline": True}
    ]

    if challenge:
        fields.insert(0, {"name": "Challenge", "value": challenge, "inline": True})

    if experiment_id:
        fields.insert(0, {"name": "Experiment", "value": experiment_id, "inline": True})

    # Create embed
    embed = _create_embed(
        title=f"🔄 Manual Relay: Agent #{agent_number} → Agent #{agent_number + 1}",
        description="Agent manually requested context relay",
        color=discord.Color.purple(),
        fields=fields
    )

    return _safe_send(channel_id, embed=embed)
