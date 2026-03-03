import streamlit as st
from openai import OpenAI
import os
from dotenv import load_dotenv

def get_agent_client():
    """
    Returns a configured OpenAI-compatible client for agents.
    Prioritizes Hugging Face Inference API if HF_TOKEN is present.
    """
    load_dotenv()
    
    # 1. Try Hugging Face (Free Inference API)
    hf_token = st.secrets.get("HF_TOKEN") or os.getenv("HF_TOKEN")
    if hf_token:
        return OpenAI(
            base_url="https://api-inference.huggingface.co/v1/",
            api_key=hf_token
        ), "mistralai/Mistral-7B-Instruct-v0.2"

    # 2. Try OpenAI (Paid)
    openai_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-3.5-turbo"

    # 3. Fallback to Local Ollama
    base_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434') + '/v1'
    return OpenAI(base_url=base_url, api_key='ollama'), "llama3.2:3b-instruct-q4_K_M"
