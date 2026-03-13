"""
Generic LLM client for web search module.
Returns parsed JSON dicts instead of (reasoning, shell_command) tuples.
"""

import os
import json
import re
from typing import Dict, Any
from urllib import request
from urllib.error import HTTPError, URLError
from dotenv import load_dotenv
from src.llm_utils.model_utils import supports_structured_output


def call_llm_json(system_prompt: str, user_prompt: str, model_name: str,
                  json_schema: dict | None = None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Call OpenRouter and parse the response as arbitrary JSON.

    Args:
        system_prompt: System message for the LLM
        user_prompt: User message with the actual task
        model_name: OpenRouter model identifier
        json_schema: Optional JSON schema to enforce structured output

    Returns:
        Tuple of (parsed_json_response, usage_dict)
    """
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not found in environment variables")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "https://localhost"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "ctf-agent"),
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "usage": {"include": True},
    }

    if json_schema and supports_structured_output(model_name):
        payload["response_format"] = json_schema

    req = request.Request(url, data=json.dumps(payload).encode("utf-8"),
                          headers=headers, method="POST")
    try:
        with request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError(f"OpenRouter HTTP error: {e.code} {e.reason}")
    except URLError as e:
        raise RuntimeError(f"OpenRouter URL error: {e.reason}")

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})

    parsed = _extract_json(content)
    return parsed, usage


def _extract_json(content: str) -> Dict[str, Any]:
    """Extract JSON from LLM response using multiple strategies."""

    # Strategy 1: Direct parse
    try:
        parsed = json.loads(content)
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code blocks
    for match in re.findall(r'```(?:json)?\s*([\[{].*?[\]}])\s*```', content, re.DOTALL):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            continue

    # Strategy 3: Find first JSON object or array in text
    for match in re.finditer(r'[\[{]', content):
        start = match.start()
        bracket = content[start]
        close = ']' if bracket == '[' else '}'
        depth = 0
        for i in range(start, len(content)):
            if content[i] == bracket:
                depth += 1
            elif content[i] == close:
                depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(content[start:i + 1])
                    if isinstance(parsed, (dict, list)):
                        return parsed
                except json.JSONDecodeError:
                    break

    # Fallback: return content as-is wrapped in a dict
    return {"raw_response": content}
