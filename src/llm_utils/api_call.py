from dotenv import load_dotenv
from src.llm_utils.openrouter import call_openrouter

def call_llm(system_prompt, user_prompt, model_name, free_api=False):
    """Invoke the OpenRouter client after loading environment variables."""
    load_dotenv()
    return call_openrouter(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_name=model_name,
        free_api=free_api,
    )
