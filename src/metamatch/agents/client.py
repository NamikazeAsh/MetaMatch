from openai import OpenAI
import os
from dotenv import load_dotenv

def get_agent_client():
    """
    Returns a configured OpenAI-compatible client for agents using local Ollama.
    """
    load_dotenv()

    base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
    return OpenAI(base_url=base_url, api_key='ollama'), "llama3.2:3b-instruct-q4_K_M"
