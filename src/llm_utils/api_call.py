from dotenv import load_dotenv
from src.llm_utils.openrouter import call_openrouter, call_openrouter_with_history

def call_llm(system_prompt, user_prompt, model_name):
    """Invoke the OpenRouter client after loading environment variables."""
    load_dotenv()
    return call_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_name=model_name,
    )

def call_llm_with_history(messages, model_name):
    """
    Call LLM with full message history for context-aware responses

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model_name: Model identifier
    Returns:
        Tuple of (reasoning, shell_command, usage) parsed from LLM response
    """
    load_dotenv()
    return call_openrouter_with_history(
        messages=messages,
        model_name=model_name,
    )
