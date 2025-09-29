#!/usr/bin/env python3
"""
CTF Agent - Main execution script
TODO: Add more features like command history, loop functionality, etc.
"""

import docker
import docker.errors
from src.llm_utils.api_call import call_llm
from src.llm_utils import prompts

# Constants
LLM_MODEL = "x-ai/grok-4-fast:free"
# LLM_MODEL = "x-ai/grok-code-fast-1"
COMMAND_TIMEOUT_SECONDS = 10
PAYED_MODELS = ["x-ai/grok-code-fast-1"]
FREE_MODELS = ["x-ai/grok-4-fast:free"]

def main():

    # Initial prompts to the LLM
    system_prompt = prompts.MAIN_SYSTEM_PROMPT
    user_prompt = prompts.MAIN_INIT_PROMPT

    # UX: Banner
    print("CTF-AGENT")
    print("==============================")

    # Choose which OpenRouter API key to use

    use_hackathon = input("Use Hackathon OPENROUTER API KEY? (y/n) [y]: ").strip().lower() or "y"
    free_api = use_hackathon != "y"  # Inverse logic: "yes" means use paid Hackathon key
    provider = "openrouter"


    # Check if model is free
    is_free = LLM_MODEL in FREE_MODELS

    # UX: Show configuration summary
    print("\nConfig options")
    print("- Provider:", provider)
    print("- Using Hackathon API:", "no" if free_api else "yes")
    print("- LLM Model:", LLM_MODEL, "(free model)" if is_free else "(paid model)")
    print(f"- Command Timeout: {COMMAND_TIMEOUT_SECONDS} seconds")
    print("==============================")

    # Call LLM provider via utils
    reasoning, shell_command = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, model_name=LLM_MODEL, free_api=free_api)
    
    # Display reasoning and command
    print(f"\n🧠 Reasoning: {reasoning}")
    print(f"💻 Shell Command: {shell_command}")
    
    # Ask for human permission
    print("\n" + "="*50)
    user_input = input("Do you want to execute this command? (y/n) [y]: ").strip().lower()
    if user_input == "" or user_input == "y":
        print("\n🚀 Executing command...")
        try:
            docker_client = docker.from_env()
            container = docker_client.containers.get("kali-linux")
            # Hardcoded timeout
            final_command = f"timeout 10s {shell_command}"

            # Simple exec with timeout
            exit_code, output = container.exec_run(["bash", "-lc", final_command])
            print("\n📤 Command Output:")
            print("-" * 30)
            text_out = output.decode().strip()
            print(text_out)
            print("-" * 30)
            if exit_code == 0:
                print("✅ Command executed successfully")
            else:
                print(f"❌ Command failed with exit code: {exit_code}")

            # No extra fallback for ls; empty output is valid for empty directories
        except docker.errors.NotFound:
            print("❌ Error: Docker container 'kali-linux' not found")
        except Exception as e:
            print(f"❌ Error executing command: {e}")
    elif user_input == "n":
        print("\n🚫 Command execution cancelled by user")
    else:
        print("❌ Command execution cancelled")


if __name__ == "__main__":
    main()
