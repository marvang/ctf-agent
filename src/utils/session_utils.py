"""Session display and summary utilities"""


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
    total_input = session["token_usage"]["input_tokens"]
    total_output = session["token_usage"]["output_tokens"]
    total_tokens = session["token_usage"]["total_tokens"]
    total_cost = session["token_usage"]["total_cost"]

    print("\n" + "="*40)
    print("🏁 Session ended")
    print(f"📊 {iterations} iterations | {len(session['commands'])} commands")
    print(f"⏱️  Elapsed time: {time_str}")
    print(f"💾 Saved: ./ctf-logs/sessions.json")
    print("="*40)
    print(f"Model used: {selected_model} 🤖")
    print("\n📈 Token Usage Summary:")
    print(f"   Input tokens:  {total_input:,}")
    print(f"   Output tokens: {total_output:,}")
    print(f"   Total tokens:  {total_tokens:,}")
    print(f"   💰 Total cost: ${total_cost:.4f}")
    print("="*40)
