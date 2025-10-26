
import os
import json
import re
from typing import Tuple, Dict, Any
from urllib import request
from urllib.error import HTTPError, URLError
from dotenv import load_dotenv
from src.llm_utils.model_utils import supports_structured_output
from src.llm_utils.response_schema import get_ctf_response_schema


def call_openrouter(system_prompt: str, user_prompt: str, model_name: str) -> Tuple[str, str, Dict[str, Any]]:

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return call_openrouter_with_history(messages=messages, model_name=model_name)


def call_openrouter_with_history(messages: list, model_name: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Call OpenRouter API with full message history for context-aware responses

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (reasoning, shell_command, usage) parsed from LLM response
    """
    load_dotenv()

    api_key_env = "OPENROUTER_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"{api_key_env} not found in environment variables")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://localhost"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "ctf-agent"),
    }

    payload = {
        "model": model_name,
        "messages": messages,
        "usage": {"include": True},
    }

    # Add structured output if model supports it
    if supports_structured_output(model_name):
        payload["response_format"] = get_ctf_response_schema()

    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError(f"OpenRouter HTTP error: {e.code} {e.reason}")
    except URLError as e:
        raise RuntimeError(f"OpenRouter URL error: {e.reason}")

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = json.dumps(data)

    # Parse JSON response - try multiple strategies
    reasoning = ""
    shell_command = ""

    # Strategy 1: Try to parse as pure JSON
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            reasoning = parsed.get("reasoning", "")
            shell_command = parsed.get("shell_command", "")

            # If we got both fields, we're done
            if reasoning and shell_command:
                usage = data.get("usage", {})
                return reasoning, shell_command, usage
    except json.JSONDecodeError:
        pass

    # Strategy 2: Try to extract JSON from markdown code blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, content, re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                reasoning = parsed.get("reasoning", "")
                shell_command = parsed.get("shell_command", "")

                if reasoning and shell_command:
                    usage = data.get("usage", {})
                    return reasoning, shell_command, usage
        except json.JSONDecodeError:
            continue

    # Strategy 3: Try to find JSON object in the text
    json_obj_pattern = r'\{[^{}]*"reasoning"[^{}]*"shell_command"[^{}]*\}'
    matches = re.findall(json_obj_pattern, content, re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                reasoning = parsed.get("reasoning", "")
                shell_command = parsed.get("shell_command", "")

                if reasoning and shell_command:
                    usage = data.get("usage", {})
                    return reasoning, shell_command, usage
        except json.JSONDecodeError:
            continue

    # Fallback: If all parsing failed, return content as reasoning
    if not reasoning:
        reasoning = content

    # Extract usage information
    usage = data.get("usage", {})

    return reasoning, shell_command, usage


