#!/usr/bin/env python3
"""
CTF Agent - Main script
"""

import os
import time
import json
from dotenv import load_dotenv
from src.llm_utils.openrouter import call_openrouter_with_history
from src.llm_utils.prompt_builder import build_initial_messages
from src.utils.state_manager import (
    init_state, get_mode, set_mode, get_state, update_state,
    append_usage_log, update_token_state,
    create_session, update_session_tokens, add_session_command, save_session,
)
from src.utils.workspace import cleanup_workspace
from src.utils.vpn import connect_to_hackthebox, disconnect_from_hackthebox
from src.utils.docker_exec import execute_command
from src.utils.docker_utils import connect_to_docker
from src.utils.session_utils import display_session_summary
from src.utils.user_interface import (
    print_banner, prompt_environment_selection, prompt_mode_selection,
    prompt_target_ip, prompt_custom_instructions, prompt_vpn_continue,
    print_config_summary
)
from src.utils.cleanup import (
    register_signal_handler, set_container, set_vpn_connected,
    set_session, is_vpn_connected, set_iteration, set_start_time, set_model
)

# Constants
COMMAND_TIMEOUT_SECONDS = 200 
MAX_COST_AUTO_MODE = 1  # Switch to semi-auto after spending $1.00
MAX_OUTPUT_LENGTH = 6000  # Character limit for what goes in the LLM, truncated if exceeded

# Workspace cleanup configuration
WORKSPACE_DIR = "./ctf-workspace"
APPROVED_FILES = [
    "connect-htb.sh",
    "disconnect-htb.sh",
    "*.ovpn",  # Keep any VPN config files
    "improvement_notes.txt"
]
FILES_TO_EMPTY = [
    "flags.txt",
    "report.txt"
]


def main():
    # Register signal handler for graceful shutdown
    register_signal_handler()
    # Load environment variables
    load_dotenv()

    # Get model from environment
    selected_model = os.getenv("OPENROUTER_MODEL")

    if not selected_model:
        print("❌ Error: OPENROUTER_MODEL not found in .env file")
        return

    # Display banner and get user selections
    print_banner()
    # use_vpn = prompt_environment_selection() # Disabled local container option for now. It was just for testing, always use HTB. TODO: re-enable it with added feature of connecting to local ctf docker containers with vulnerable services.
    use_vpn = True
    
    selected_mode = prompt_mode_selection()

    # Initialize state
    init_state(mode=selected_mode)

    # Clean up workspace files from previous sessions
    if not cleanup_workspace(WORKSPACE_DIR, APPROVED_FILES, FILES_TO_EMPTY):
        return

    # Connect to Docker first
    _, container = connect_to_docker()
    if container is None:
        return
    set_container(container)

    # Handle VPN connection if requested
    if use_vpn:
        if not connect_to_hackthebox(container):
            if not prompt_vpn_continue():
                return
        else:
            set_vpn_connected(True)

        target_ip = prompt_target_ip()
        if not target_ip:
            return
        

        target_info = target_ip
    else:
        target_info = "Local container"

    # Create session
    session = create_session(model=selected_model, mode=selected_mode)
    set_session(session)
    set_model(selected_model)

    # Display configuration summary
    print_config_summary(target_info, selected_mode)

    # Get custom instructions and build initial messages
    custom_instructions = prompt_custom_instructions()
    messages = build_initial_messages(use_vpn, target_info, custom_instructions)

    iteration = 0

    # Track session start time
    session_start_time = time.time()
    set_start_time(session_start_time)

    while True:
        iteration += 1
        set_iteration(iteration)  # Update iteration count for cleanup handler
        current_mode = get_mode()

        # Check if auto mode has exceeded cost limit
        current_session_cost = session["token_usage"]["total_cost"]
        if current_mode == "auto" and current_session_cost >= MAX_COST_AUTO_MODE:
            print(f"\n⚠️  Auto mode reached cost limit of ${MAX_COST_AUTO_MODE:.2f}!")
            print(f"💰 Current session cost: ${current_session_cost:.4f}")
            print("🔄 Switching to Semi-Auto mode for cost control...")
            set_mode("semi-auto")
            current_mode = "semi-auto"

        # Check if flag was found (watcher detected it)
        state = get_state()
        if state.get("flag_found", False) and current_mode == "semi-auto":
            print(f"\n{'='*60}")
            print("🏴‍☠️🎉🏆 FLAG DETECTED by AGENT! 🏆🎉🏴‍☠️")
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
        print(f"\n{'='*40}")
        print(f"{mode_emoji} Iteration {iteration}")
        print('='*40)

        # Call LLM with full chat history
        try:
            reasoning, shell_command, usage = call_openrouter_with_history(
                messages=messages,
                model_name=selected_model,
            )
        except Exception as e:
            print(f"❌ LLM API error: {e}")
            break

        # Display LLM response
        print(f"\n🧠 {reasoning}")
        print(f"💻 {shell_command}")

        # Track token usage (log to file and update totals)
        if usage:
            append_usage_log(usage, selected_model)
            update_token_state(usage, selected_model)
            update_session_tokens(session, usage)

        # Check for exit command - only when LLM explicitly requests termination
        shell_cmd_clean = shell_command.strip()
        if shell_cmd_clean.lower() in ["exit", "quit", "terminate"]:
            print("\n✅ Agent requested termination. Exiting...")
            break

        if not shell_command.strip():
            print("\n⚠️  No command provided")
            retry_choice = input("❓ Retry? (y/n) [n]: ").strip().lower()
            if retry_choice == "y":
                messages.append({"role": "user", "content": "No command was provided or the syntax was not correct and the json was not able to be parsed. Please provide a shell command to execute."})
                continue
            else:
                print("\n👋 Exiting...")
                break

        # Add assistant response to history
        assistant_message = {
            "role": "assistant",
            "content": json.dumps({"reasoning": reasoning, "shell_command": shell_command})
        }
        messages.append(assistant_message)

        # Execute based on mode
        should_execute = False

        if current_mode == "semi-auto":
            # Ask for permission
            user_input = input("\n▶️  Execute? (y/n/quit) [y]: ").strip().lower()
            if user_input == "quit" or user_input == "q":
                print("\n👋 Exiting...")
                break
            elif user_input == "" or user_input == "y":
                should_execute = True
            else:
                print("⏭️  Skipped")
        else:
            # Fully-auto mode
            should_execute = True
            print(f"\n🤖 Executing...")

        # Execute command
        if should_execute:
            success, output, exit_code = execute_command(container, shell_command, COMMAND_TIMEOUT_SECONDS)

            # Add to session log with full output and reasoning
            add_session_command(session, shell_command, output, exit_code, reasoning)

            # Limit output for LLM context (keep last MAX_OUTPUT_LENGTH characters)
            if len(output) > MAX_OUTPUT_LENGTH:
                truncated_output = output[-MAX_OUTPUT_LENGTH:]
                truncation_warning = f"[WARNING: Output truncated. Showing last {MAX_OUTPUT_LENGTH} of {len(output)} characters]\n\n"
                llm_output = truncation_warning + truncated_output
            else:
                llm_output = output

            # Add command result to chat history
            result_message = {
                "role": "user",
                "content": f"Command executed with exit code {exit_code}. Output:\n{llm_output}"
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

    # Disconnect VPN if it was connected
    if is_vpn_connected():
        disconnect_from_hackthebox(container)

    # Calculate elapsed time and display summary
    session_end_time = time.time()
    elapsed_seconds = session_end_time - session_start_time
    display_session_summary(session, iteration, elapsed_seconds, selected_model)


if __name__ == "__main__":
    main()
