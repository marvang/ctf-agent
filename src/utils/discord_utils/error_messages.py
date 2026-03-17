"""
Discord Integration - Error Messages
Handles error and alert notifications.
"""

from typing import Any

import discord

from .core import _create_embed, _safe_send


def send_llm_error_message(channel_id, error_msg: str, context: dict[str, Any]) -> bool:
    """
    Send LLM API error alert notification.

    Args:
        channel_id: Discord channel ID
        error_msg: Error message from LLM API
        context: Context dict with optional keys:
            - challenge: Challenge name
            - iteration: Current iteration
            - model: Model name
            - experiment_id: Experiment ID

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_llm_error_message(
        ...     channel_id="123456789",
        ...     error_msg="API rate limit exceeded",
        ...     context={
        ...         "challenge": "vm0",
        ...         "iteration": 15,
        ...         "model": "x-ai/grok-4.1-fast:free"
        ...     }
        ... )
    """
    if not channel_id:
        return False

    # Truncate error message if too long
    if len(error_msg) > 500:
        error_msg = error_msg[:497] + "..."

    # Build fields from context
    fields = []

    if "challenge" in context:
        fields.append({"name": "Challenge", "value": context["challenge"], "inline": True})

    if "model" in context:
        fields.append({"name": "Model", "value": context["model"], "inline": True})

    if "iteration" in context:
        fields.append({"name": "Iteration", "value": str(context["iteration"]), "inline": True})

    if "experiment_id" in context:
        fields.append({"name": "Experiment", "value": context["experiment_id"], "inline": True})

    # Add error message
    fields.append({"name": "Error", "value": f"```{error_msg}```", "inline": False})

    embed = _create_embed(
        title="🤖❌ LLM API Error",
        description="LLM API call failed - experiment may be stopping",
        color=discord.Color.red(),
        fields=fields,
    )

    return _safe_send(channel_id, embed=embed)


def send_empty_command_stop_message(
    channel_id,
    context: dict[str, Any],
    retry_limit: int = 5,
) -> bool:
    """
    Send empty command stop notification.

    Args:
        channel_id: Discord channel ID
        context: Context dict with optional keys:
            - challenge: Challenge name
            - iteration: Current iteration
            - experiment_id: Experiment ID
        retry_limit: Number of consecutive empty commands before stopping

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_empty_command_stop_message(
        ...     channel_id="123456789",
        ...     context={
        ...         "challenge": "vm0",
        ...         "iteration": 8,
        ...         "experiment_id": "20250527_143022"
        ...     },
        ...     retry_limit=5,
        ... )
    """
    if not channel_id:
        return False

    # Build fields from context
    fields = []

    if "challenge" in context:
        fields.append({"name": "Challenge", "value": context["challenge"], "inline": True})

    if "iteration" in context:
        fields.append({"name": "Iteration", "value": str(context["iteration"]), "inline": True})

    if "experiment_id" in context:
        fields.append({"name": "Experiment", "value": context["experiment_id"], "inline": True})

    embed = _create_embed(
        title="❌ Agent Stopped: Empty Commands",
        description=f"Agent provided empty command {retry_limit} times consecutively and was stopped",
        color=discord.Color.red(),
        fields=fields,
    )

    return _safe_send(channel_id, embed=embed)


def send_docker_connection_error_message(channel_id, container_name: str, context: dict[str, Any]) -> bool:
    """
    Send Docker connection error notification.

    Args:
        channel_id: Discord channel ID
        container_name: Name of container that failed to connect
        context: Context dict with optional keys:
            - challenge: Challenge name
            - experiment_id: Experiment ID

    Returns:
        True if successful, False otherwise

    Example:
        >>> send_docker_connection_error_message(
        ...     channel_id="123456789",
        ...     container_name="ctf-agent-pic-demo-kali",
        ...     context={
        ...         "challenge": "vm0",
        ...         "experiment_id": "20250527_143022"
        ...     }
        ... )
    """
    if not channel_id:
        return False

    # Build fields from context
    fields = [{"name": "Container", "value": container_name, "inline": True}]

    if "challenge" in context:
        fields.insert(0, {"name": "Challenge", "value": context["challenge"], "inline": True})

    if "experiment_id" in context:
        fields.append({"name": "Experiment", "value": context["experiment_id"], "inline": True})

    embed = _create_embed(
        title="🐳❌ Docker Connection Failed",
        description="Failed to connect to Docker container - experiment cannot continue",
        color=discord.Color.red(),
        fields=fields,
    )

    return _safe_send(channel_id, embed=embed)
