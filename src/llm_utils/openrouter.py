
import os
import json
from typing import Tuple
from urllib import request
from urllib.error import HTTPError, URLError
from dotenv import load_dotenv


def call_openrouter(system_prompt: str, user_prompt: str, model_name: str) -> Tuple[str, str]:
    """
    Single-shot call with system and user prompts (backward compatibility)
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return call_openrouter_with_history(messages=messages, model_name=model_name)


def call_openrouter_with_history(messages: list, model_name: str) -> Tuple[str, str]:
    """
    Call OpenRouter API with full message history for context-aware responses

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (reasoning, shell_command) parsed from LLM response
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
    }

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

    # Attempt to parse JSON with keys reasoning/shell_command; otherwise fallback
    reasoning = content
    shell_command = ""
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            if "reasoning" in parsed:
                reasoning = parsed.get("reasoning", reasoning)
            if "shell_command" in parsed:
                shell_command = parsed.get("shell_command", "")
    except Exception:
        pass

    return reasoning, shell_command


