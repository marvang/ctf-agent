#!/usr/bin/env python3
"""
CTF Agent - Main execution script
TODO: Add more features like command history, loop functionality, etc.
"""

import os
import json
import docker
from dotenv import load_dotenv
from groq import Groq


def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    
    if not api_key:
        print("Error: GROQ_API_KEY not found in environment variables")
        return
    
    # Initialize Groq client
    model_name = "openai/gpt-oss-120b"
    client = Groq(api_key=api_key)
    
    # Get LLM reasoning and shell command
    print("🤖 CTF Agent is reasoning...")
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "You are a CTF-agent designed to autonomously navigate environments and perform standard CTF tasks and find flags."
            },
            {
                "role": "user",
                "content": (
                    "you are dropped in a new environment."
                    "Reason first and then provide the next logical shell command. "
                    "Respond with JSON: {\"reasoning\": \"your_reasoning_here\", \"shell_command\": \"your_command_here\"}"
                )
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "shell_command",
                "schema": {
                    "type": "object",
                    "properties": {
                        "reasoning": {"type": "string"},
                        "shell_command": {"type": "string"}
                    },
                    "required": ["reasoning", "shell_command"],
                    "additionalProperties": False
                }
            }
        }
    )
    
    # Parse LLM response
    result = json.loads(response.choices[0].message.content)
    reasoning = result["reasoning"]
    shell_command = result["shell_command"]
    
    # Display reasoning and command
    print(f"\n🧠 Reasoning: {reasoning}")
    print(f"💻 Shell Command: {shell_command}")
    
    # Ask for human permission
    print("\n" + "="*50)
    user_input = input("Do you want to execute this command? (yes/no): ").strip().lower()
    
    if user_input == "yes":
        print("\n🚀 Executing command...")
        
        # Initialize Docker client and execute command
        try:
            docker_client = docker.from_env()
            container = docker_client.containers.get("kali-linux")
            
            # Execute the command
            exit_code, output = container.exec_run(
                ["bash", "-lc", shell_command]
            )
            
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
    else:
        print("❌ Command execution cancelled")


if __name__ == "__main__":
    main()