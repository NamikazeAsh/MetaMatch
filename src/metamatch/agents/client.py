from openai import OpenAI
import os
from dotenv import load_dotenv

DEFAULT_MODEL = "llama3.2:3b-instruct-q4_K_M"


def get_agent_client():
    """
    Returns a configured OpenAI-compatible client for agents using local Ollama.
    Set LLM_MODEL in .env to try another pulled model (e.g. gemma3:4b).
    """
    load_dotenv()

    base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
    model = os.getenv('LLM_MODEL') or DEFAULT_MODEL
    return OpenAI(base_url=base_url, api_key='ollama'), model
