#!/usr/bin/env python3
"""
CTF Agent - Main execution script with auto/semi-auto modes and chat history
"""

import docker
import docker.errors
from src.llm_utils.api_call import call_llm_with_history
from src.llm_utils import prompts
from src.utils.state_manager import init_state, get_mode, set_mode

# Constants
DEFAULT_LLM_MODEL = "x-ai/grok-4-fast:free" # free
COMMAND_TIMEOUT_SECONDS = 10
PAYED_MODELS = ["x-ai/grok-code-fast-1", "anthropic/claude-sonnet-4.5", "openai/gpt-5", "openai/gpt-5-mini", "openai/gpt-5-nano"]
FREE_MODELS = ["x-ai/grok-4-fast:free"]
MAX_ITERATIONS = 5  # Prevent infinite loops
API_PROVIDER = "openrouter"
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
    # UX: Banner
    print("🤖 CTF-AGENT v1.2")
    print("==============================")

    # Model selection
    print("\n📋 Select model:")
    all_models = FREE_MODELS + PAYED_MODELS
    
    for i, model in enumerate(all_models, 1):
        cost_label = "(FREE)" if model in FREE_MODELS else ""
        print(f"{i}. {model} {cost_label}")
    
    while True:
        model_choice = input(f"Enter choice (1-{len(all_models)}) [1]: ").strip() or "1"
        try:
            choice_idx = int(model_choice) - 1
            if 0 <= choice_idx < len(all_models):
                selected_model = all_models[choice_idx]
                is_free = selected_model in FREE_MODELS
                break
            else:
                print("❌ Invalid choice. Please try again.")
        except ValueError:
            print("❌ Please enter a valid number.")
    
    # Configure API settings
    provider = API_PROVIDER

    # Mode selection
    print("\n📋 Select mode:")
    print("1. Semi-Auto")
    print(f"2. ⚠️  Fully-Auto, max {MAX_ITERATIONS} iterations)")
    
    mode_choice = input("Enter choice (1/2) [1]: ").strip() or "1"

    if mode_choice == "2":
        selected_mode = "auto"
        print(f"⚠️  Fully-Auto mode selected (will revert to Semi-Auto after {MAX_ITERATIONS} iterations)")
    else:
        selected_mode = "semi-auto"
        print("✅ Semi-Auto mode selected")

    # Initialize state
    init_state(mode=selected_mode)

    # Config summary
    print("\n⚙️  Configuration:")
    print(f"   • Mode: {selected_mode}")
    print(f"   • Provider: {provider}")
    print(f"   • LLM Model: {selected_model} {'(free)' if is_free else '(paid)'}")
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
        from src.utils.state_manager import get_state
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
                from src.utils.state_manager import update_state
                update_state(flag_found=False)

        mode_emoji = "🤖" if current_mode == "auto" else "👤"
        print(f"\n{'='*60}")
        print(f"Iteration #{iteration} | Mode: {mode_emoji} {current_mode.upper()}")
        print('='*60)

        # Call LLM with full chat history
        try:
            reasoning, shell_command = call_llm_with_history(
                messages=messages,
                model_name=selected_model,
            )
        except Exception as e:
            print(f"❌ LLM API error: {e}")
            break

        # Display LLM response
        print(f"\n🧠 Reasoning: {reasoning}")
        print(f"💻 Shell Command: {shell_command}")

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

            # Add command result to chat history
            result_message = {
                "role": "user",
                "content": f"Command executed with exit code {exit_code}. Output:\n{output}"
            }
            messages.append(result_message)
        else:
            # Add skipped message to history
            skip_message = {
                "role": "user",
                "content": "Command was not executed (skipped by user)."
            }
            messages.append(skip_message)

    # End of loop
    print("\n" + "="*60)
    print("🏁 CTF Agent session ended.")
    print(f"📊 Total iterations: {iteration}")
    print("="*60)


if __name__ == "__main__":
    main()
