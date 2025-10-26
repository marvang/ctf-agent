#!/usr/bin/env python3
"""
CTF Agent - Main execution script
"""

import os
import docker
import docker.errors
import subprocess
import time
import signal
import sys
import re
from dotenv import load_dotenv
from src.llm_utils.api_call import call_llm_with_history
from src.llm_utils import prompts
from src.utils.state_manager import (
    init_state, get_mode, set_mode, get_state, update_state,
    append_usage_log, update_token_state,
    create_session, update_session_tokens, add_session_command, save_session
)
from src.utils.workspace import cleanup_workspace
from src.utils.vpn import connect_to_hackthebox, disconnect_from_hackthebox
from src.utils.docker_exec import execute_command

# Constants
COMMAND_TIMEOUT_SECONDS = 200  # Ger mer tid för nätverksscanning och NMAP
MAX_COST_AUTO_MODE = 0.03  # Switch to semi-auto after spending $1.00
MAX_OUTPUT_LENGTH = 6000  # Maximum characters of output to send to LLM

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

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    print('\\n\\n🛑 Avbryter programmet...')
    print('👋 Stänger ner Docker-anslutningar...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


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


def main():
    # Load environment variables
    load_dotenv()

    # Get model from environment
    selected_model = os.getenv("OPENROUTER_MODEL")

    if not selected_model:
        print("❌ Error: OPENROUTER_MODEL not found in .env file")
        return

    # UX: Banner
    print("🤖 CTF-AGENT v1.4")
    print("="*40)

    # Environment selection
    print("\n🌐 Environment:")
    print("1. Local container")
    print("2. HackTheBox")

    env_choice = input("Choose (1/2) [2]: ").strip() or "2"

    use_vpn = env_choice in ["2"]
    target_info = ""
    target_ip = ""

    # Mode selection
    print("\n🤖 Mode:")
    print("1. Auto")
    print("2. Semi-Auto")

    mode_choice = input("Choose (1/2) [1]: ").strip() or "1"

    if mode_choice == "2":
        selected_mode = "semi-auto"
    else:
        selected_mode = "auto"

    # Initialize state
    init_state(mode=selected_mode)

    # Clean up workspace files from previous sessions
    if not cleanup_workspace(WORKSPACE_DIR, APPROVED_FILES, FILES_TO_EMPTY):
        return

    # Connect to Docker first
    try:
        docker_client = docker.from_env()
        container = docker_client.containers.get("kali-linux")
        print("\n✅ Docker connected")
    except docker.errors.NotFound:
        print("\n❌ Docker container 'kali-linux' not found")
        print("💡 Run: docker compose up -d")
        return
    except Exception as e:
        print(f"\n❌ Docker error: {e}")
        return

    # Handle VPN connection if requested
    vpn_connected = False  # Track VPN connection status for cleanup
    if use_vpn:
        if not connect_to_hackthebox(container):
            continue_choice = input("\n⚠️  VPN failed. Continue? (y/n) [n]: ").strip().lower()
            if continue_choice != "y":
                return
        else:
            vpn_connected = True  # Mark VPN as successfully connected

        # Now ask for target IP after VPN is connected
        target_ip = input("\n🎯 Target IP: ").strip()
        
        # Simple IP validation: only dots and digits
        if not target_ip:
            print("❌ Target IP is required for HackTheBox environment. Exiting...")
            return
        elif not re.match(r'^[\d.]+$', target_ip):
            print("❌ Invalid IP format. IP should only contain digits and dots. Exiting...")
            return
        
        target_info = f"{target_ip}"
    else:
        target_info = "Local container"

    # Create session
    session = create_session(model=selected_model, mode=selected_mode)

    # Config summary
    print(f"\n⚙️  Target: {target_info} | Mode: {selected_mode}")
    print("="*40)

    # Initialize chat history with appropriate prompt based on environment
    if use_vpn:
        if env_choice == "2":
            # Use HackTheBox-aware prompt
            system_prompt = prompts.HACKTHEBOX_SYSTEM_PROMPT
            environment_context = f"Environment: HackTheBox: VPN Connected. This is the only allowed target, The target ip address is: {target_info} "
    else:
        # Use original simple prompt for local environment
        system_prompt = prompts.MAIN_SYSTEM_PROMPT
        environment_context = f"Environment: {target_info} (Local Mode)\\nThis is a local container environment. Explore files and local services."

    # Allow user to customize initial instructions
    print("\n📝 Initial Instructions:")
    print("="*40)
    custom_instructions = input("Add custom instructions? (press Enter to skip): ").strip()
    
    if custom_instructions:
        print(f"✅ Custom instructions added")
        initial_user_prompt = f"{environment_context}\\n\\n{prompts.MAIN_INIT_PROMPT}\\n\\nADDITIONAL CUSTOM INSTRUCTIONS FROM THE TEAM: {custom_instructions}"
    else:
        initial_user_prompt = f"{environment_context}\\n\\n{prompts.MAIN_INIT_PROMPT}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_prompt}
    ]

    iteration = 0

    # Track session tokens
    session_input_tokens = 0
    session_output_tokens = 0

    # Track session start time
    session_start_time = time.time()

    while True:
        iteration += 1
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
            reasoning, shell_command, usage = call_llm_with_history(
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
            session_input_tokens += usage.get("prompt_tokens", 0)
            session_output_tokens += usage.get("completion_tokens", 0)
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
            "content": f'{{"reasoning": "{reasoning}", "shell_command": "{shell_command}"}}'
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
            success, output, exit_code = execute_command(docker_client, container, shell_command, COMMAND_TIMEOUT_SECONDS)

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
    if vpn_connected:
        disconnect_from_hackthebox(container)

    # Calculate elapsed time and display summary
    session_end_time = time.time()
    elapsed_seconds = session_end_time - session_start_time
    display_session_summary(session, iteration, elapsed_seconds, selected_model)


if __name__ == "__main__":
    main()
