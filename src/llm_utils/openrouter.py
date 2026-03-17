import json
import os
import re
import time
from http.client import IncompleteRead
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from dotenv import load_dotenv

from src.llm_utils.response_schema import get_ctf_response_schema


def _call_openrouter_api(messages: list, model_name: str, response_schema: dict) -> dict:
    """Send a request to the OpenRouter API with retry logic.

    Handles API key loading, request construction, and retries (3 attempts)
    for HTTPError, URLError, IncompleteRead, and TimeoutError.

    Returns the parsed JSON response dict from the API.
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
    }

    payload = {
        "model": model_name,
        "messages": messages,
        "usage": {"include": True},
        "response_format": response_schema,
    }

    encoded_payload = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=encoded_payload, headers=headers, method="POST")

    max_attempts = 3
    last_error_details = None

    for attempt in range(1, max_attempts + 1):
        try:
            with request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data
        except HTTPError as e:
            error_details = {
                "http_code": e.code,
                "http_reason": e.reason,
                "attempt": attempt,
            }
            try:
                error_body = e.read().decode("utf-8")
                error_json = json.loads(error_body)
                if "error" in error_json:
                    error_details["message"] = error_json["error"].get("message")
                    error_details["metadata"] = error_json["error"].get("metadata")
                else:
                    error_details["raw_response"] = error_body
            except Exception:
                error_details["raw_response"] = str(e)

            last_error_details = error_details

            if attempt < max_attempts:
                print(
                    f"⚠️  OpenRouter HTTP error (attempt {attempt}/{max_attempts}): {e.code} {e.reason}. Retrying in 2s..."
                )
                time.sleep(2)
                req = request.Request(url, data=encoded_payload, headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}") from None
        except URLError as e:
            last_error_details = {
                "error_type": "URLError",
                "reason": str(e.reason),
                "attempt": attempt,
            }

            if attempt < max_attempts:
                print(f"⚠️  OpenRouter URL error (attempt {attempt}/{max_attempts}): {e.reason}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=encoded_payload, headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}") from None
        except IncompleteRead as e:
            last_error_details = {
                "error_type": "IncompleteRead",
                "bytes_read": str(e.partial) if hasattr(e, "partial") else str(e),
                "attempt": attempt,
            }

            if attempt < max_attempts:
                print(f"⚠️  OpenRouter incomplete read (attempt {attempt}/{max_attempts}): {e}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=encoded_payload, headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}") from None
        except TimeoutError as e:
            last_error_details = {
                "error_type": "Timeout",
                "message": str(e),
                "attempt": attempt,
            }

            if attempt < max_attempts:
                print(f"⚠️  OpenRouter timeout (attempt {attempt}/{max_attempts}): {e}. Retrying in 2s...")
                time.sleep(2)
                req = request.Request(url, data=encoded_payload, headers=headers, method="POST")
            else:
                raise RuntimeError(f"OpenRouter API error: {json.dumps(last_error_details)}") from None

    # Should not be reached, but satisfy type checkers
    raise RuntimeError("OpenRouter API error: exhausted all retry attempts")


def parse_llm_error(exception: Exception) -> dict:
    """Parse structured error details from an LLM API exception.

    Attempts to extract JSON error metadata from RuntimeError messages
    raised by _call_openrouter_api. Falls back to a raw_error dict.
    """
    error_str = str(exception)
    if "OpenRouter API error:" in error_str:
        try:
            json_start = error_str.index("{")
            return json.loads(error_str[json_start:])
        except (ValueError, json.JSONDecodeError):
            return {"raw_error": error_str}
    return {"raw_error": error_str}


def _extract_openrouter_message_fields(data: dict) -> tuple[str, str]:
    """Return normalized message content and separate reasoning text."""
    try:
        message = data["choices"][0]["message"]
    except Exception:
        return json.dumps(data), ""

    content = message.get("content")
    reasoning = message.get("reasoning", "") or ""

    if content is None:
        return "", reasoning
    if isinstance(content, str):
        return content, reasoning
    return json.dumps(content), reasoning


def _parse_json_fields(content: str, fields: list[str]) -> dict[str, str] | None:
    """Try multiple strategies to extract named fields from LLM response content.

    Returns a dict of extracted fields if parsing succeeds and 'reasoning' is non-empty,
    or None if all strategies fail.
    """

    def _try_extract(text: str) -> dict[str, str] | None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        result = {f: parsed.get(f, "") for f in fields}
        if result.get("reasoning"):
            return result
        return None

    # Strategy 1: Pure JSON
    result = _try_extract(content)
    if result is not None:
        return result

    # Strategy 2: JSON inside markdown code blocks
    for match in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL):
        result = _try_extract(match)
        if result is not None:
            return result

    # Strategy 3: Bare JSON object containing "reasoning"
    for match in re.findall(r'\{[^{}]*"reasoning"[^{}]*\}', content, re.DOTALL):
        result = _try_extract(match)
        if result is not None:
            return result

    return None


def call_openrouter_with_history(messages: list, model_name: str) -> tuple[str, str, dict[str, Any], str]:
    """
    Call OpenRouter API with full message history for context-aware responses.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (reasoning, shell_command, usage, extended_reasoning) parsed from LLM response
    """
    data = _call_openrouter_api(messages, model_name, get_ctf_response_schema())
    content, extended_reasoning = _extract_openrouter_message_fields(data)
    usage = data.get("usage", {})

    result = _parse_json_fields(content, ["reasoning", "shell_command"])
    if result is not None:
        return result["reasoning"], result["shell_command"], usage, extended_reasoning

    return content, "", usage, extended_reasoning


def call_openrouter_with_history_pty(
    messages: list, model_name: str
) -> tuple[str, str, str, dict[str, Any], str]:
    """Call OpenRouter API with PTY-mode schema (reasoning, shell_command, stdin_input).

    Returns:
        Tuple of (reasoning, shell_command, stdin_input, usage, extended_reasoning)
    """
    from src.llm_utils.response_schema import get_ctf_pty_response_schema

    data = _call_openrouter_api(messages, model_name, get_ctf_pty_response_schema())
    content, extended_reasoning = _extract_openrouter_message_fields(data)
    usage = data.get("usage", {})

    result = _parse_json_fields(content, ["reasoning", "shell_command", "stdin_input"])
    if result is not None:
        return result["reasoning"], result["shell_command"], result["stdin_input"], usage, extended_reasoning

    return content, "", "", usage, extended_reasoning


# For Protocol Generation - structured output with reasoning + protocol
def call_openrouter_protocol(messages: list, model_name: str) -> tuple[str, str, dict[str, Any]]:
    """
    Call OpenRouter API for protocol generation with structured output.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_name: OpenRouter model identifier

    Returns:
        Tuple of (reasoning, protocol, usage) parsed from LLM response
    """
    from src.llm_utils.response_schema import get_protocol_response_schema

    data = _call_openrouter_api(messages, model_name, get_protocol_response_schema())

    # Parse JSON response
    content, reasoning = _extract_openrouter_message_fields(data)
    protocol = ""

    if content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                reasoning = parsed.get("reasoning", reasoning)
                protocol = parsed.get("protocol", "")
        except json.JSONDecodeError:
            # Fallback: use raw content as protocol if structured parsing fails
            protocol = content

    if not protocol and not content:
        protocol = content

    usage = data.get("usage", {})
    return reasoning, protocol, usage
