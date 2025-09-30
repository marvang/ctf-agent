#!/usr/bin/env python3
"""
CTF Agent - Main execution script
"""

import os
import docker
import docker.errors
from dotenv import load_dotenv
from src.llm_utils.api_call import call_llm_with_history
from src.llm_utils import prompts
from src.utils.state_manager import (
    init_state, get_mode, set_mode, get_state, update_state,
    append_usage_log, update_token_state, get_model_token_state,
    create_session, update_session_tokens, add_session_command, save_session
)

# Constants
COMMAND_TIMEOUT_SECONDS = 30
MAX_ITERATIONS = 15  # Prevent infinite loops
INITIAL_MESSAGES = [
    {"role": "system", "content": prompts.MAIN_SYSTEM_PROMPT},
    {"role": "user", "content": prompts.MAIN_INIT_PROMPT}
]


def execute_command(docker_client, container, shell_command):
    """
    Execute shell command in Docker container

    Returns:
        Tuple of (success: bool, output: str, exit_code: int)
    """
    try:
        final_command = f"timeout {COMMAND_TIMEOUT_SECONDS}s {shell_command}"
        exit_code, output = container.exec_run(["bash", "-lc", final_command])

        text_out = output.decode().strip()
        success = exit_code == 0

        print("\n📤 Command Output:")
        print("-" * 30)
        print(text_out)
        print("-" * 30)

        if success:
            print("✅ Command executed successfully")
        else:
            print(f"⚠️  Command exit code: {exit_code}")

        return success, text_out, exit_code

    except docker.errors.NotFound:
        error_msg = "❌ Error: Docker container 'kali-linux' not found"
        print(error_msg)
        return False, error_msg, -1
    except Exception as e:
        error_msg = f"❌ Error executing command: {e}"
        print(error_msg)
        return False, error_msg, -1


def main():
    # Load environment variables
    load_dotenv()

    # Get model from environment
    selected_model = os.getenv("OPENROUTER_MODEL")
    if not selected_model:
        print("❌ Error: OPENROUTER_MODEL not found in .env file")
        return

    # UX: Banner
    print("🤖 CTF-AGENT v1.2")
    print("==============================")

    # Mode selection
    print("1. Auto")
    print(f"2. semi-Auto")

    mode_choice = input("Enter choice (1/2) [1]: ").strip() or "1"

    if mode_choice == "2":
        selected_mode = "semi-auto"
    else:
        selected_mode = "auto"

    # Initialize state
    init_state(mode=selected_mode)

    # Clean up workspace files from previous sessions
    workspace_files_to_clean = [
        "./ctf-workspace/flags.txt",
        "./ctf-workspace/reports.txt"
    ]
    files_exist = [f for f in workspace_files_to_clean if os.path.exists(f)]
    if files_exist:
        print(f"\n🧹 Found leftover files from previous sessions:")
        for f in files_exist:
            print(f"   • {f}")
        wipe_choice = input("Do you want to wipe them? (y/n) [y]: ").strip().lower()
        if wipe_choice == "" or wipe_choice == "y":
            for file_path in files_exist:
                try:
                    os.remove(file_path)
                    print(f"✅ Cleaned up: {file_path}")
                except Exception as e:
                    print(f"⚠️  Could not clean {file_path}: {e}")
        else:
            print("⏭️  Keeping existing files")

    # Create session
    session = create_session(model=selected_model, mode=selected_mode)
    print(f"\n🆔 Session ID: {session['id']}")

    # Config summary
    print("\n⚙️  Configuration:")
    print(f"   • Mode: {selected_mode}")
    print(f"   • LLM Model: {selected_model}")
    print(f"   • Command Timeout: {COMMAND_TIMEOUT_SECONDS}s")
    print("==============================")

    # Initialize chat history
    messages = INITIAL_MESSAGES.copy()

    # Connect to Docker
    try:
        docker_client = docker.from_env()
        container = docker_client.containers.get("kali-linux")
        print("\n✅ Connected to Docker container 'kali-linux'")
    except docker.errors.NotFound:
        print("\n❌ Error: Docker container 'kali-linux' not found")
        return
    except Exception as e:
        print(f"\n❌ Error connecting to Docker: {e}")
        return

    iteration = 0
    auto_iteration_count = 0  # Track iterations in fully-auto mode
    initial_mode = selected_mode

    # Track session tokens
    session_input_tokens = 0
    session_output_tokens = 0

    while True:
        iteration += 1
        current_mode = get_mode()

        # Check if fully-auto has reached its iteration limit
        if initial_mode == "auto" and auto_iteration_count >= MAX_ITERATIONS and current_mode == "auto":
            print(f"\n⚠️  Fully-Auto mode reached {MAX_ITERATIONS} iterations limit!")
            print("🔄 Switching to Semi-Auto mode for safety...")
            set_mode("semi-auto")
            current_mode = "semi-auto"
            initial_mode = "semi-auto"  # Don't revert back

        # Increment auto counter if in auto mode
        if current_mode == "auto":
            auto_iteration_count += 1

        # Check if flag was found (watcher detected it)
        state = get_state()
        if state.get("flag_found", False) and current_mode == "semi-auto":
            print(f"\n{'='*60}")
            print("🎉 FLAG DETECTED by watcher!")
            print('='*60)
            quit_choice = input("🤔 Do you want to quit the session? (y/n) [n]: ").strip().lower()
            if quit_choice == "y":
                print("\n👋 User requested quit after flag detection. Exiting...")
                break
            else:
                print("✅ Continuing session...")
                # Reset flag_found so we don't ask again
                update_state(flag_found=False)

        mode_emoji = "🤖" if current_mode == "auto" else "👤"
        print(f"\n{'='*60}")
        print(f"Iteration #{iteration} | Mode: {mode_emoji} {current_mode.upper()}")
        print('='*60)

        # Call LLM with full chat history
        try:
            reasoning, shell_command, usage = call_llm_with_history(
                messages=messages,
                model_name=selected_model,
            )
        except Exception as e:
            print(f"❌ LLM API error: {e}")
            break

        # Display LLM response
        print(f"\n🧠 Reasoning: {reasoning}")
        print(f"💻 Shell Command: {shell_command}")

        # Track token usage (log to file and update totals)
        if usage:
            append_usage_log(usage, selected_model)
            session_input_tokens += usage.get("prompt_tokens", 0)
            session_output_tokens += usage.get("completion_tokens", 0)
            update_token_state(usage, selected_model)
            update_session_tokens(session, usage)

        # Check for exit command
        if shell_command.strip().lower() in ["exit", "quit", "terminate"]:
            print("\n✅ Agent requested termination. Exiting...")
            break

        if not shell_command.strip():
            print("\n⚠️  No command provided by LLM.")
            retry_choice = input("❓ Continue and retry? (y/n) [n]: ").strip().lower()
            if retry_choice == "y":
                print("🔄 Retrying...")
                messages.append({"role": "user", "content": "No command was provided. Please provide a shell command to execute."})
                continue
            else:
                print("\n👋 Exiting due to no command...")
                break

        # Add assistant response to history
        assistant_message = {
            "role": "assistant",
            "content": f'{{"reasoning": "{reasoning}", "shell_command": "{shell_command}"}}'
        }
        messages.append(assistant_message)

        # Execute based on mode
        should_execute = False

        if current_mode == "semi-auto":
            # Ask for permission
            print("\n" + "="*50)
            user_input = input("▶️  Execute this command? (y/n/quit) [y]: ").strip().lower()
            if user_input == "quit" or user_input == "q":
                print("\n👋 User requested quit. Exiting...")
                break
            elif user_input == "" or user_input == "y":
                should_execute = True
            else:
                print("\n⏭️  Command skipped by user")
        else:
            # Fully-auto mode
            should_execute = True
            print(f"\n🤖 [AUTO {auto_iteration_count}/5] Executing command...")

        # Execute command
        if should_execute:
            success, output, exit_code = execute_command(docker_client, container, shell_command)

            # Add to session log with full output and reasoning
            add_session_command(session, shell_command, output, exit_code, reasoning)

            # Limit output to last 5000 characters for LLM context
            truncated_output = output[-5000:] if len(output) > 5000 else output
            if len(output) > 5000:
                print(f"⚠️  Output truncated to last 5000 characters for LLM (original: {len(output)} chars)")

            # Add command result to chat history
            result_message = {
                "role": "user",
                "content": f"Command executed with exit code {exit_code}. Output:\n{truncated_output}"
            }
            messages.append(result_message)
        else:
            # Add skipped message to history
            skip_message = {
                "role": "user",
                "content": "Command was not executed (skipped by user)."
            }
            messages.append(skip_message)

    # End of loop - Save session and show summary
    save_session(session)

    print("\n" + "="*60)
    print("🏁 CTF Agent session ended.")
    print(f"🆔 Session ID: {session['id']}")
    print(f"📊 Total iterations: {iteration}")

    # Display session token usage summary
    session_total_tokens = session_input_tokens + session_output_tokens
    print(f"\n📈 Session Token Usage ({selected_model}):")
    print(f"   • Input tokens: {session_input_tokens}")
    print(f"   • Output tokens: {session_output_tokens}")
    print(f"   • Total tokens: {session_total_tokens}")
    print(f"   • Commands executed: {len(session['commands'])}")

    # Display overall model statistics across all sessions
    overall_state = get_model_token_state(selected_model)
    print(f"\n📊 Overall Model Statistics ({selected_model}):")
    print(f"   • Total requests (all sessions): {overall_state.get('request_count', 0)}")
    print(f"   • Total tokens (all sessions): {overall_state.get('total_tokens', 0)}")
    print(f"   • Estimated total cost: {overall_state.get('total_cost', 0):.6f} credits")

    print(f"\n💾 Session saved to: ./ctf-logs/sessions.json")
    print("="*60)


if __name__ == "__main__":
    main()
