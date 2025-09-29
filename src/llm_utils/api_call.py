
import os
import json
from dotenv import load_dotenv
from groq import Groq
from src.llm_utils.groq import call_groq
from src.llm_utils.openrouter import call_openrouter

API_PROVIDER = "groq"

def call_llm(system_prompt, user_prompt, model_name, provider=API_PROVIDER, free_api=False):
    # Load environment variables
    load_dotenv()
    if provider == "groq":
        return call_groq(system_prompt=system_prompt, user_prompt=user_prompt, model_name=model_name)
    elif provider == "openrouter":
        return call_openrouter(system_prompt=system_prompt, user_prompt=user_prompt, model_name=model_name, free_api=free_api)
    else:
        raise ValueError(f"Unsupported provider: {provider}")