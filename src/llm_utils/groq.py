import os
import json
from dotenv import load_dotenv
from groq import Groq


def call_groq(system_prompt, user_prompt, model_name):
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError("GROQ_API_KEY not found in environment variables")

    client = Groq(api_key=api_key)

    print("🤖 CTF Agent is reasoning...")
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
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

    result = json.loads(response.choices[0].message.content)
    reasoning = result["reasoning"]
    shell_command = result["shell_command"]
    return reasoning, shell_command