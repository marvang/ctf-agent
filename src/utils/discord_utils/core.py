"""
Discord Integration - Core Module
Handles bot client initialization, channel management, and message sending helpers.
"""

import asyncio
import os
import re
from typing import Any

import discord
from dotenv import load_dotenv

load_dotenv()

# Environment variables
DISCORD_MAIN_BOT_TOKEN = os.getenv("DISCORD_MAIN_BOT_TOKEN", "")
DISCORD_LLM_AGENT_BOT_TOKEN = os.getenv("DISCORD_LLM_AGENT_BOT_TOKEN", "")
DISCORD_TERMINAL_BOT_TOKEN = os.getenv("DISCORD_TERMINAL_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
DISCORD_PARENT_CATEGORY_ID = os.getenv("DISCORD_PARENT_CATEGORY_ID", "")

# Event loop reference
_event_loop: asyncio.AbstractEventLoop | None = None


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create event loop for async operations."""
    global _event_loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Loop is closed")
        _event_loop = loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _event_loop = loop
    return _event_loop


def _get_bot_token(bot_type: str) -> str:
    if bot_type == "summary":
        return DISCORD_MAIN_BOT_TOKEN
    elif bot_type == "llm_agent":
        return DISCORD_LLM_AGENT_BOT_TOKEN
    elif bot_type == "terminal":
        return DISCORD_TERMINAL_BOT_TOKEN
    return ""


def _create_client() -> discord.Client:
    """Create a fresh Discord client with required intents."""
    intents = discord.Intents.default()
    intents.guilds = True
    intents.message_content = True
    return discord.Client(intents=intents)


async def _async_create_channel(experiment_id: str) -> str | None:
    """
    Create a new Discord channel for experiment tracking.

    Args:
        experiment_id: Unique experiment identifier

    Returns:
        Channel ID as string, or None if failed
    """
    if not DISCORD_MAIN_BOT_TOKEN or not DISCORD_GUILD_ID:
        return None

    client = _create_client()

    try:
        await client.login(DISCORD_MAIN_BOT_TOKEN)

        # Get guild
        guild = await client.fetch_guild(int(DISCORD_GUILD_ID))

        if not guild:
            print(f"❌ Guild not found: {DISCORD_GUILD_ID}")
            return None

        # Get parent category if specified
        category = None
        if DISCORD_PARENT_CATEGORY_ID:
            try:
                category = await client.fetch_channel(int(DISCORD_PARENT_CATEGORY_ID))
                print(f"📂 Using category: {category.name}")  # type: ignore[union-attr]
            except Exception as e:
                print(f"⚠️  Could not fetch category {DISCORD_PARENT_CATEGORY_ID}: {e}")
                print("   Channel will be created without a category")

        channel_name = re.sub(r"[^a-z0-9_-]", "-", experiment_id.lower())[:100]
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,  # type: ignore[arg-type]
            topic=f"Run {experiment_id}",
        )

        print(f"✅ Discord channel created: #{channel.name} (ID: {channel.id})")
        return str(channel.id)

    except Exception as e:
        print(f"❌ Failed to create Discord channel: {e}")
        return None
    finally:
        await client.close()
        # Give aiohttp time to clean up the session
        await asyncio.sleep(0.25)


async def _async_create_challenge_channel(category_id: str, challenge_name: str) -> str | None:
    if not DISCORD_MAIN_BOT_TOKEN or not DISCORD_GUILD_ID:
        return None

    client = _create_client()

    try:
        await client.login(DISCORD_MAIN_BOT_TOKEN)

        guild = await client.fetch_guild(int(DISCORD_GUILD_ID))

        if not guild:
            return None

        category = await client.fetch_channel(int(category_id))

        if not category:
            return None

        channel_name = f"challenge-{challenge_name}"
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,  # type: ignore[arg-type]
            topic=f"Live logging for challenge: {challenge_name}",
        )

        print(f"✅ Challenge channel created: #{channel.name} (ID: {channel.id})")
        return str(channel.id)

    except Exception as e:
        print(f"❌ Failed to create challenge channel: {e}")
        return None
    finally:
        await client.close()
        await asyncio.sleep(0.25)


async def _async_send_message(
    channel_id: str, content: str | None = None, embed: discord.Embed | None = None, bot_type: str = "summary"
) -> bool:
    token = _get_bot_token(bot_type)
    if not token:
        return False

    client = _create_client()

    try:
        await client.login(token)

        channel = await client.fetch_channel(int(channel_id))

        if not channel:
            print(f"❌ Channel not found: {channel_id}")
            return False

        await channel.send(content=content, embed=embed)  # type: ignore[arg-type, union-attr]
        return True

    except Exception as e:
        print(f"❌ Failed to send Discord message: {e}")
        return False
    finally:
        await client.close()
        await asyncio.sleep(0.25)


def _run_async(coro: Any) -> Any:
    """
    Helper to run async coroutine in sync context.

    Args:
        coro: Async coroutine to run

    Returns:
        Result of coroutine
    """
    loop = _get_or_create_event_loop()

    if loop.is_running():
        print("⚠️  Event loop already running - skipping Discord operation")
        return None
    else:
        return loop.run_until_complete(coro)


def create_experiment_channel(experiment_id: str) -> str | None:
    """
    Create a new Discord channel for experiment tracking.

    Sync wrapper around async channel creation.

    Args:
        experiment_id: Unique experiment identifier (e.g., "20250527_143022")

    Returns:
        Channel ID as string, or None if failed/disabled

    Example:
        >>> channel_id = create_experiment_channel("20250527_143022")
        >>> if channel_id:
        ...     print(f"Channel created: {channel_id}")
    """
    if not DISCORD_MAIN_BOT_TOKEN or not DISCORD_GUILD_ID:
        # Silently skip if not configured
        return None

    try:
        result: str | None = _run_async(_async_create_channel(experiment_id))
        return result
    except Exception as e:
        print(f"❌ Error creating Discord channel: {e}")
        return None


def create_challenge_channel(category_id: str, challenge_name: str) -> str | None:
    if not DISCORD_MAIN_BOT_TOKEN or not DISCORD_GUILD_ID:
        return None

    try:
        result: str | None = _run_async(_async_create_challenge_channel(category_id, challenge_name))
        return result
    except Exception as e:
        print(f"❌ Error creating challenge channel: {e}")
        return None


def _safe_send(
    channel_id: str, content: str | None = None, embed: discord.Embed | None = None, bot_type: str = "summary"
) -> bool:
    if not channel_id:
        return False

    token = _get_bot_token(bot_type)
    if not token or not DISCORD_GUILD_ID:
        return False

    try:
        return _run_async(_async_send_message(channel_id, content, embed, bot_type)) or False
    except Exception as e:
        print(f"❌ Error sending Discord message: {e}")
        return False


def _create_embed(
    title: str, description: str, color: discord.Color, fields: list[dict[str, Any]] | None = None
) -> discord.Embed:
    """
    Helper to create formatted Discord embed.

    Args:
        title: Embed title
        description: Embed description
        color: Embed color
        fields: List of dicts with 'name', 'value', 'inline' keys

    Returns:
        Discord embed object
    """
    embed = discord.Embed(title=title, description=description, color=color)

    if fields:
        for field in fields:
            embed.add_field(name=field.get("name", ""), value=field.get("value", ""), inline=field.get("inline", False))

    return embed
