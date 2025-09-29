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
LLM_MODEL = "x-ai/grok-code-fast-1"
def main():

    # Initial prompts to the LLM
    system_prompt = prompts.MAIN_SYSTEM_PROMPT
    user_prompt = prompts.MAIN_INIT_PROMPT

    # UX: Banner
    print("CTF-AGENT")
    print("==============================")

    # Choose provider and free vs paid

    provider_input = input("Choose provider groq (g)/openrouter (o) [openrouter]: ").strip().lower()
    if provider_input in ["g", "groq"]:
        provider = "groq"
    elif provider_input in ["o", "openrouter", ""]:
        provider = "openrouter"
    else:
        print("Invalid input, defaulting to openrouter.")
        provider = "openrouter"
    free_choice = "n"
    if provider == "openrouter":
        free_choice = input("Use FREE OpenRouter API? (y/n) [y]: ").strip().lower() or "y"
    free_api = provider == "openrouter" and free_choice == "y"

    # UX: Show configuration summary
    print("\nConfig options")
    print("- Provider:", provider)
    print("- Free API:", "yes" if free_api else "no")
    print("- LLM Model:", LLM_MODEL)
    print("==============================")

    # Call LLM provider via utils
    reasoning, shell_command = call_llm(system_prompt=system_prompt, user_prompt=user_prompt, model_name=LLM_MODEL, provider=provider, free_api=free_api)
    
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
            # Execute the command
            exit_code, output = container.exec_run([
                "bash", "-lc", shell_command
            ])
            # Print output
            print("\n📤 Command Output:")
            print("-" * 30)
            print(output.decode().strip())
            print("-" * 30)
            if exit_code == 0:
                print("✅ Command executed successfully")
            else:
                print(f"❌ Command failed with exit code: {exit_code}")
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