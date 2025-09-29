
import os
import json
from typing import Tuple
from urllib import request
from urllib.error import HTTPError, URLError
from dotenv import load_dotenv


def call_openrouter(system_prompt: str, user_prompt: str, model_name: str, free_api: bool = False) -> Tuple[str, str]:
    load_dotenv()
    
    api_key_env = "OPENROUTER_FREE_KEY" if free_api else "OPENROUTER_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise RuntimeError(f"{api_key_env} not found in environment variables")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Optional: identify your app; safe to omit if unknown
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://localhost"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "ctf-agent"),
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError(f"OpenRouter HTTP error: {e.code} {e.reason}")
    except URLError as e:
        raise RuntimeError(f"OpenRouter URL error: {e.reason}")

    # Try to align return with Groq: (reasoning, shell_command)
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


