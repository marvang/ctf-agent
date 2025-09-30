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
from dotenv import load_dotenv
from src.llm_utils.api_call import call_llm_with_history
from src.llm_utils import prompts
from src.utils.state_manager import (
    init_state, get_mode, set_mode, get_state, update_state,
    append_usage_log, update_token_state, get_model_token_state,
    create_session, update_session_tokens, add_session_command, save_session
)

# Constants
#COMMAND_TIMEOUT_SECONDS = 30
COMMAND_TIMEOUT_SECONDS = 120 # Ger mer tid för nätverksscanning och NMAP
MAX_ITERATIONS = 15  # Prevent infinite loops
INITIAL_MESSAGES = [
    {"role": "system", "content": prompts.MAIN_SYSTEM_PROMPT},
    {"role": "user", "content": prompts.MAIN_INIT_PROMPT}
]

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    print('\\n\\n🛑 Avbryter programmet...')
    print('👋 Stänger ner Docker-anslutningar...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


def check_vpn_connection(container):
    """
    Check if VPN is already connected by looking for tun interface
    """
    try:
        exit_code, output = container.exec_run(["bash", "-c", "ip link show | grep tun"])
        return exit_code == 0
    except Exception:
        return False


def connect_to_hackthebox(container):
    """
    Attempt to connect to HackTheBox VPN using the connect script
    """
    print("\n🔗 Attempting to connect to HackTheBox VPN...")
    try:
        # Check if VPN config exists
        exit_code, _ = container.exec_run(["test", "-f", "/ctf-workspace/hackthebox.ovpn"])
        if exit_code != 0:
            print("❌ HackTheBox VPN config not found at /ctf-workspace/hackthebox.ovpn")
            print("💡 Please copy your .ovpn file to ctf-workspace/hackthebox.ovpn")
            return False
        
        # Run connection script
        exit_code, output = container.exec_run([
            "bash", "-c", 
            "cd /ctf-workspace && timeout 30s ./connect-htb.sh"
        ])
        
        output_text = output.decode().strip()
        print(output_text)
        
        # Wait a bit for connection to establish
        time.sleep(5)
        
        # Verify connection
        if check_vpn_connection(container):
            print("✅ Successfully connected to HackTheBox VPN!")
            
            # Test connectivity to common HackTheBox subnets
            print("\n🔍 Testing connectivity to HackTheBox network...")
            test_targets = ["10.10.10.1", "10.10.11.1"]
            
            for target in test_targets:
                exit_code, _ = container.exec_run([
                    "bash", "-c", 
                    f"timeout 5s ping -c 1 {target} > /dev/null 2>&1"
                ])
                if exit_code == 0:
                    print(f"✅ Can reach {target}")
                    break
            else:
                print("⚠️  Could not ping common HackTheBox IPs, but VPN appears connected")
            
            return True
        else:
            print("❌ VPN connection failed or tun interface not found")
            return False
            
    except Exception as e:
        print(f"❌ Error during VPN connection: {e}")
        return False


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

    except KeyboardInterrupt:
        print("\\n\\n⚠️  Kommando avbrutet av användare (Ctrl+C)")
        return False, "Command interrupted by user", -1
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

    # Get model and target IP from environment
    selected_model = os.getenv("OPENROUTER_MODEL")
    target_ip = os.getenv("TARGET_IP", "10.129.80.148")  # Fallback to default
    
    if not selected_model:
        print("❌ Error: OPENROUTER_MODEL not found in .env file")
        return

    # UX: Banner
    print("🤖 CTF-AGENT v1.4 - Med HackTheBox Support")
    print("===========================================")
    
    # Environment selection
    print("\n🌐 Välj miljö:")
    print("1. Lokal miljö (standard)")
    print("2. HackTheBox - Meow (Starting Point)")
    print("3. HackTheBox - Anpassad target (Avancerat)")
    
    env_choice = input("Välj miljö (1/2/3) [1]: ").strip() or "1"
    
    use_vpn = env_choice in ["2", "3"]
    target_info = ""
    
    if env_choice == "2":
        target_info = f"Meow ({target_ip})"
    elif env_choice == "3":
        custom_ip = input("Ange target IP: ").strip()
        if custom_ip:
            target_ip = custom_ip  # Override the default target IP
            target_info = f"Custom target ({target_ip})"
        else:
            print("❌ Target IP krävs för anpassad miljö")
            return
    else:
        target_info = "Lokal container miljö"

    # Mode selection
    print("\n🤖 Välj körläge:")
    print("1. Auto (kör kommandon automatiskt)")
    print("2. Semi-Auto (frågar innan varje kommando)")

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
    print(f"   • Target: {target_info}")
    print(f"   • VPN: {'Enabled' if use_vpn else 'Disabled'}")
    print(f"   • Mode: {selected_mode}")
    print(f"   • LLM Model: {selected_model}")
    print(f"   • Command Timeout: {COMMAND_TIMEOUT_SECONDS}s")
    print("==========================================")

    # Initialize chat history with appropriate prompt based on environment
    if use_vpn:
        if env_choice == "2":
            # Use HackTheBox-aware prompt with Telnet expertise for Meow
            system_prompt = prompts.HACKTHEBOX_SYSTEM_PROMPT
            environment_context = f"Environment: {target_info} (VPN Connected)"
            environment_context += f"\\nTarget: HackTheBox Starting Point - Meow. Target IP: {target_ip}\\nStart by scanning this specific IP: nmap -sCV -T4 {target_ip}"
        elif env_choice == "3":
            # Use advanced ATTACKER_PROMPT for custom targets
            system_prompt = prompts.ATTACKER_PROMPT.replace("{kali_prompt}", prompts.kali_prompt)
            environment_context = f"Environment: {target_info} (VPN Connected)\\nTarget: {target_ip}\\nStart with network reconnaissance of the target: nmap -sCV -T4 {target_ip}"
    else:
        # Use original simple prompt for local environment
        system_prompt = prompts.MAIN_SYSTEM_PROMPT
        environment_context = f"Environment: {target_info} (Local Mode)\\nThis is a local container environment. Explore files and local services."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{environment_context}\\n\\n{prompts.MAIN_INIT_PROMPT}"}
    ]

    # Connect to Docker
    try:
        docker_client = docker.from_env()
        container = docker_client.containers.get("kali-linux")
        print("\n✅ Connected to Docker container 'kali-linux'")
    except docker.errors.NotFound:
        print("\n❌ Error: Docker container 'kali-linux' not found")
        print("💡 Run: docker compose up -d")
        return
    except Exception as e:
        print(f"\n❌ Error connecting to Docker: {e}")
        return

    # Handle VPN connection if requested
    if use_vpn:
        if not connect_to_hackthebox(container):
            print("\n⚠️  VPN connection failed. Continue anyway? (y/n) [n]: ", end="")
            continue_choice = input().strip().lower()
            if continue_choice != "y":
                print("👋 Exiting due to VPN connection failure...")
                return
            else:
                print("⚠️  Continuing without VPN connection...")
        else:
            print("\n🎯 Ready to hack! VPN connected and target accessible.")
    else:
        print("\n🏠 Running in local mode - ready to explore container environment.")

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

        # Check for exit command - handle both simple exit and complex commands ending with exit
        shell_cmd_clean = shell_command.strip()
        if (shell_cmd_clean.lower() in ["exit", "quit", "terminate"] or 
            shell_cmd_clean.endswith("; exit") or 
            shell_cmd_clean.endswith(";exit") or
            shell_cmd_clean.endswith("exit'") or
            "exit'" in shell_cmd_clean):
            print("\n✅ Agent requested termination. Exiting...")
            # If this is a complex command that saves flag and exits, execute it first
            if len(shell_cmd_clean) > 10 and ("flags.txt" in shell_cmd_clean or "reports.txt" in shell_cmd_clean):
                print("🏁 Executing final flag-saving command before exit...")
                success, output, exit_code = execute_command(docker_client, container, shell_command)
                add_session_command(session, shell_command, output, exit_code, reasoning)
                print("✅ Flag and report saved successfully!")
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
