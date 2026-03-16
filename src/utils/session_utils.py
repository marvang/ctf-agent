"""Session display and summary utilities"""


def _count_session_commands(session: dict) -> int:
    """Count executed commands across replay events, with legacy fallback."""
    events = session.get("events")
    if isinstance(events, list):
        return sum(
            1
            for event in events
            if isinstance(event, dict) and event.get("tag") == "assistant_command"
        )

    commands = session.get("commands")
    if isinstance(commands, list):
        return len(commands)

    return 0


def display_session_summary(session: dict, iterations: int, elapsed_seconds: float, selected_model: str):
    """Display final session statistics"""
    elapsed_minutes = elapsed_seconds / 60
    elapsed_hours = elapsed_minutes / 60

    # Format elapsed time
    if elapsed_hours >= 1:
        time_str = f"{elapsed_hours:.2f} hours"
    elif elapsed_minutes >= 1:
        time_str = f"{elapsed_minutes:.2f} minutes"
    else:
        time_str = f"{elapsed_seconds:.2f} seconds"

    # Get final token and cost info from session
    total_input = session["metrics"]["total_input_tokens"]
    total_output = session["metrics"]["total_output_tokens"]
    total_tokens = session["metrics"]["total_tokens"]
    total_cost = session["metrics"]["total_cost"]
    command_count = _count_session_commands(session)

    print("\n" + "="*40)
    print("🏁 Session ended")
    print(f"📊 {iterations} iterations | {command_count} commands")
    print(f"⏱️  Elapsed time: {time_str}")
    print("="*40)
    print(f"Model used: {selected_model} 🤖")
    print("\n📈 Token Usage Summary:")
    print(f"   Input tokens:  {total_input:,}")
    print(f"   Output tokens: {total_output:,}")
    print(f"   Total tokens:  {total_tokens:,}")
    print(f"   💰 Total cost: ${total_cost:.4f}")
    print("="*40)
