"""
JSON schema definitions for structured model responses
"""


def get_ctf_response_schema() -> dict:
    """JSON schema enforcing {reasoning, shell_command} responses."""
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
                        "description": "The reasoning behind the command choice and approach",
                    },
                    "shell_command": {
                        "type": "string",
                        "description": "The shell command to execute in the CTF environment",
                    },
                },
                "required": ["reasoning", "shell_command"],
                "additionalProperties": False,
            },
        },
    }


def get_ctf_pty_response_schema() -> dict:
    """JSON schema enforcing {reasoning, shell_command, stdin_input} responses for PTY mode."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ctf_pty_command_response",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "The reasoning behind the command choice and approach",
                    },
                    "shell_command": {
                        "type": "string",
                        "description": "The shell command to execute in the CTF environment, or empty string to send stdin_input instead",
                    },
                    "stdin_input": {
                        "type": "string",
                        "description": "Text to send to a running interactive session (e.g. password), or empty string when running a new command",
                    },
                },
                "required": ["reasoning", "shell_command", "stdin_input"],
                "additionalProperties": False,
            },
        },
    }


def get_protocol_response_schema() -> dict:
    """JSON schema enforcing {reasoning, protocol} responses."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "relay_protocol_response",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                        "description": "Reasoning and analysis of penetration testing session, chain of thought regarding the protocol generation approach and key decisions",
                    },
                    "protocol": {
                        "type": "string",
                        "description": "The markdown relay protocol content to be appended to the initial prompt for the next agent",
                    },
                },
                "required": ["reasoning", "protocol"],
                "additionalProperties": False,
            },
        },
    }
