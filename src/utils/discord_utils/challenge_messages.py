"""
Discord Integration - Challenge Messages
Handles challenge-level notifications (start, complete, error).
"""

import discord
from typing import Dict, Any, Optional
from .core import _safe_send, _create_embed


def send_challenge_start_message(channel_id, challenge: str, index: int, total: int, target_ip: Optional[str] = None) -> bool:
    """
    Send challenge start notification.

    Args:
        channel_id: Discord channel ID
        challenge: Challenge name
        index: Challenge index (1-based)
        total: Total number of challenges
        target_ip: Target IP address (optional)

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_challenge_start_message(
        ...     channel_id="123456789",
        ...     challenge="vm0",
        ...     index=1,
        ...     total=5,
        ...     target_ip="192.168.5.0"
        ... )
    """
    if not channel_id:
        return False

    description = f"Starting challenge {index} of {total}"
    if target_ip:
        description += f"\nTarget: `{target_ip}`"

    content = f"🎯 **Challenge Started: {challenge}**\n{description}"

    return _safe_send(channel_id, content=content)


def send_challenge_complete_message(channel_id, challenge: str, result: Dict[str, Any]) -> bool:
    """
    Send challenge completion notification with metrics.

    Args:
        channel_id: Discord channel ID
        challenge: Challenge name
        result: Challenge result dict with keys:
            - flag_captured: String or None
            - flag_valid: Boolean
            - iterations: Int
            - relay_count: Int
            - total_cost: Float
            - total_time: Float
            - stopping_reason: String
            - session: Dict (optional, for agent number)
            - relay_triggers: List (optional, for relay breakdown)
            - llm_error_details: Dict (optional, for error info)

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_challenge_complete_message(
        ...     channel_id="123456789",
        ...     challenge="vm0",
        ...     result={
        ...         "flag_captured": "HTB{...}",
        ...         "flag_valid": True,
        ...         "iterations": 15,
        ...         "relay_count": 2,
        ...         "total_cost": 2.50,
        ...         "total_time": 450.0,
        ...         "stopping_reason": "agent_exit",
        ...         "session": {"agent_number": 2},
        ...         "relay_triggers": [{"trigger_type": "auto"}, {"trigger_type": "manual"}]
        ...     }
        ... )
    """
    if not channel_id:
        return False

    # Extract result values
    flag_captured = result.get("flag_captured", None)
    flag_valid = result.get("flag_valid", False)
    iterations = result.get("iterations", 0)
    relay_count = result.get("relay_count", 0)
    total_cost = result.get("total_cost", 0.0)
    total_time = result.get("total_time", 0.0)
    stopping_reason = result.get("stopping_reason", "unknown")

    # Extract enhanced info
    session = result.get("session", {})
    relay_triggers = session.get("relay_triggers", []) if session else []
    llm_error_details = result.get("llm_error_details")
    agent_number = session.get("agent_number", 0) if session else 0

    # Determine status
    if flag_valid:
        status = "✅ Success"
        color = discord.Color.green()
        title_emoji = "🎉"
    elif flag_captured:
        status = "⚠️ Invalid Flag"
        color = discord.Color.orange()
        title_emoji = "❓"
    else:
        status = "❌ Failed"
        color = discord.Color.red()
        title_emoji = "💔"

    # Format time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    time_str = f"{minutes}m {seconds}s"

    # Create fields
    fields = [
        {"name": "Status", "value": status, "inline": True},
        {"name": "Iterations", "value": str(iterations), "inline": True},
        {"name": "Relays", "value": str(relay_count), "inline": True},
        {"name": "Cost", "value": f"${total_cost:.2f}", "inline": True},
        {"name": "Time", "value": time_str, "inline": True},
        {"name": "Stopping Reason", "value": stopping_reason, "inline": True}
    ]

    # Add agent number if CHAP was used (relay_count > 0 means CHAP)
    if relay_count > 0:
        fields.append({"name": "Final Agent", "value": f"Agent #{agent_number}", "inline": True})

    # Add relay breakdown if relays occurred
    if relay_triggers:
        auto_count = sum(1 for r in relay_triggers if r.get("trigger_type") == "auto")
        manual_count = sum(1 for r in relay_triggers if r.get("trigger_type") == "manual")
        relay_breakdown = f"{auto_count} auto, {manual_count} manual"
        fields.append({"name": "Relay Breakdown", "value": relay_breakdown, "inline": True})

    # Add LLM error details if present
    if llm_error_details and stopping_reason == "llm_error":
        error_info = llm_error_details.get("raw_error", "Unknown error")
        # Truncate if too long
        if len(error_info) > 200:
            error_info = error_info[:197] + "..."
        fields.append({"name": "LLM Error", "value": f"```{error_info}```", "inline": False})

    # Add flag info if captured
    if flag_captured:
        flag_display = flag_captured if len(flag_captured) <= 50 else flag_captured[:47] + "..."
        fields.append({"name": "Flag", "value": f"`{flag_display}`", "inline": False})

    # Create embed
    embed = _create_embed(
        title=f"{title_emoji} Challenge Complete: {challenge}",
        description=f"Challenge finished with {iterations} iterations",
        color=color,
        fields=fields
    )

    return _safe_send(channel_id, embed=embed)


def send_challenge_error_message(channel_id, challenge: str, error_msg: str, experiment_id: Optional[str] = None) -> bool:
    """
    Send challenge error notification.

    Args:
        channel_id: Discord channel ID
        challenge: Challenge name
        error_msg: Error message
        experiment_id: Experiment ID (optional)

    Returns:
        True if successful, False otherwise
    """
    if not channel_id:
        return False

    # Truncate error message if too long
    if len(error_msg) > 500:
        error_msg = error_msg[:497] + "..."

    fields = [
        {"name": "Challenge", "value": challenge, "inline": True},
        {"name": "Error", "value": f"```{error_msg}```", "inline": False}
    ]

    if experiment_id:
        fields.insert(1, {"name": "Experiment", "value": experiment_id, "inline": True})

    embed = _create_embed(
        title="❌ Challenge Error",
        description="Challenge failed with error",
        color=discord.Color.red(),
        fields=fields
    )

    return _safe_send(channel_id, embed=embed)
