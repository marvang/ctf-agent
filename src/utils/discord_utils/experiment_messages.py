"""
Discord Integration - Experiment Messages
Handles experiment-level notifications (start, complete, interrupted, error).
"""

import discord
from typing import Dict, Any, List
from .core import _safe_send, _create_embed


def send_experiment_start_message(channel_id, experiment_id: str, config: dict) -> bool:
    """
    Send experiment start notification.

    Args:
        channel_id: Discord channel ID
        experiment_id: Unique experiment identifier
        config: Experiment configuration dict with keys:
            - model: Model name
            - chap_enabled: Boolean
            - challenges: List of challenge names
            - max_iterations: Int
            - max_cost: Float

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_experiment_start_message(
        ...     channel_id="123456789",
        ...     experiment_id="20250527_143022",
        ...     config={
        ...         "model": "x-ai/grok-4.1-fast:free",
        ...         "chap_enabled": True,
        ...         "challenges": ["vm0", "vm2"],
        ...         "max_iterations": 40,
        ...         "max_cost": 5.0
        ...     }
        ... )
    """
    if not channel_id:
        return False

    # Extract config values
    model = config.get("model", "Unknown")
    chap_enabled = config.get("chap_enabled", False)
    challenges = config.get("challenges", [])
    max_iterations = config.get("max_iterations", 0)
    max_cost = config.get("max_cost", 0.0)

    # Format challenges list
    if isinstance(challenges, list):
        challenges_str = ", ".join(challenges[:5])  # Show first 5
        if len(challenges) > 5:
            challenges_str += f" ... (+{len(challenges) - 5} more)"
    else:
        challenges_str = str(challenges)

    # Create embed
    embed = _create_embed(
        title=f"🚀 Experiment Started: {experiment_id}",
        description="CTF Agent experiment run initiated",
        color=discord.Color.blue(),
        fields=[
            {"name": "Model", "value": model, "inline": True},
            {"name": "CHAP Enabled", "value": "✅ Yes" if chap_enabled else "❌ No", "inline": True},
            {"name": "Challenge Count", "value": str(len(challenges) if isinstance(challenges, list) else 0), "inline": True},
            {"name": "Max Iterations", "value": str(max_iterations), "inline": True},
            {"name": "Max Cost", "value": f"${max_cost:.2f}", "inline": True},
            {"name": "Challenges", "value": challenges_str, "inline": False}
        ]
    )

    return _safe_send(channel_id, embed=embed)


def send_experiment_complete_message(channel_id, results: List[Dict[str, Any]], metadata: dict) -> bool:
    """
    Send experiment completion summary.

    Args:
        channel_id: Discord channel ID
        results: List of challenge result dicts
        metadata: Experiment metadata dict with keys:
            - total_challenges: Int
            - successful: Int
            - failed: Int
            - total_cost: Float
            - total_time: Float
            - valid_flags: Int
            - termination_reason: String (optional)

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_experiment_complete_message(
        ...     channel_id="123456789",
        ...     results=[...],
        ...     metadata={
        ...         "total_challenges": 5,
        ...         "successful": 3,
        ...         "failed": 2,
        ...         "total_cost": 12.50,
        ...         "total_time": 3600.0,
        ...         "valid_flags": 3
        ...     }
        ... )
    """
    if not channel_id:
        return False

    # Extract metadata
    total = metadata.get("total_challenges", 0)
    successful = metadata.get("successful", 0)
    failed = metadata.get("failed", 0)
    total_cost = metadata.get("total_cost", 0.0)
    total_time = metadata.get("total_time", 0.0)
    valid_flags = metadata.get("valid_flags", 0)
    termination_reason = metadata.get("termination_reason", "completed")

    # Determine color based on success rate
    if successful == total:
        color = discord.Color.green()
        status_emoji = "✅"
    elif successful > 0:
        color = discord.Color.orange()
        status_emoji = "⚠️"
    else:
        color = discord.Color.red()
        status_emoji = "❌"

    # Format time
    hours = int(total_time // 3600)
    minutes = int((total_time % 3600) // 60)
    seconds = int(total_time % 60)
    time_str = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

    # Create description
    description = f"{status_emoji} Experiment completed"
    if termination_reason and termination_reason != "completed":
        description += f" ({termination_reason})"

    # Create embed
    embed = _create_embed(
        title=f"🏁 Experiment Complete",
        description=description,
        color=color,
        fields=[
            {"name": "Success Rate", "value": f"{successful}/{total} ({(successful/total*100) if total > 0 else 0:.1f}%)", "inline": True},
            {"name": "Valid Flags", "value": f"🏁 {valid_flags}/{total}", "inline": True},
            {"name": "Total Cost", "value": f"💰 ${total_cost:.2f}", "inline": True},
            {"name": "Total Time", "value": f"⏱️ {time_str}", "inline": True},
            {"name": "Successful", "value": f"✅ {successful}", "inline": True},
            {"name": "Failed", "value": f"❌ {failed}", "inline": True}
        ]
    )

    return _safe_send(channel_id, embed=embed)


def send_experiment_interrupted_message(channel_id, partial_results: int, total_challenges: int) -> bool:
    """
    Send experiment interruption notification.

    Args:
        channel_id: Discord channel ID
        partial_results: Number of completed challenges
        total_challenges: Total number of planned challenges

    Returns:
        True if successful, False otherwise
    """
    if not channel_id:
        return False

    embed = _create_embed(
        title="⚠️ Experiment Interrupted",
        description="Experiment was interrupted by user",
        color=discord.Color.orange(),
        fields=[
            {"name": "Progress", "value": f"{partial_results}/{total_challenges} challenges completed", "inline": False}
        ]
    )

    return _safe_send(channel_id, embed=embed)


def send_experiment_error_message(channel_id, error_msg: str, partial_results: int = 0) -> bool:
    """
    Send experiment fatal error notification.

    Args:
        channel_id: Discord channel ID
        error_msg: Error message
        partial_results: Number of completed challenges before error

    Returns:
        True if successful, False otherwise
    """
    if not channel_id:
        return False

    # Truncate error message if too long
    if len(error_msg) > 500:
        error_msg = error_msg[:497] + "..."

    embed = _create_embed(
        title="❌ Experiment Failed",
        description="Experiment aborted due to unexpected error",
        color=discord.Color.red(),
        fields=[
            {"name": "Error", "value": f"```{error_msg}```", "inline": False},
            {"name": "Completed", "value": f"{partial_results} challenges", "inline": False}
        ]
    )

    return _safe_send(channel_id, embed=embed)
