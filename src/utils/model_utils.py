"""
Model utilities for checking capabilities and features
"""

def supports_structured_output(model_name: str) -> bool:
    """
    Check if a model supports structured JSON schema output.

    Currently, only OpenAI GPT models and X.AI Grok models support structured outputs.
    Claude models rely on instruction following for JSON formatting.

    Args:
        model_name: The model identifier (e.g., "openai/gpt-4", "anthropic/claude-3")

    Returns:
        True if model supports structured outputs, False otherwise
    """
    model_lower = model_name.lower()

    # OpenAI GPT models support structured outputs
    if "openai/" in model_lower or "gpt" in model_lower:
        return True

    # X.AI Grok models support structured outputs
    if "x-ai/" in model_lower or "grok" in model_lower:
        return True

    # Anthropic Claude models do not support structured outputs
    if "anthropic/" in model_lower or "claude" in model_lower:
        return False

    # Default to False for unknown models (safer to rely on instruction following)
    return False


def is_claude_model(model_name: str) -> bool:
    """
    Check if a model is an Anthropic Claude model.

    Args:
        model_name: The model identifier

    Returns:
        True if it's a Claude model, False otherwise
    """
    model_lower = model_name.lower()
    return "anthropic/" in model_lower or "claude" in model_lower