"""
JSON schema definitions for structured model responses
"""

def get_ctf_response_schema() -> dict:
    """
    Get the JSON schema for CTF agent responses.

    This schema enforces that models return a structured response with:
    - reasoning: The model's thought process
    - shell_command: The command to execute

    Returns:
        Dictionary containing the response_format configuration for OpenRouter
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ctf_command_response",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "The reasoning behind the command choice and approach"
                    },
                    "shell_command": {
                        "type": "string",
                        "description": "The shell command to execute in the CTF environment"
                    }
                },
                "required": ["reasoning", "shell_command"],
                "additionalProperties": False
            }
        }
    }