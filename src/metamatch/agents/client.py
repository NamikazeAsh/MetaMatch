from openai import OpenAI
import os
import time
import urllib.request
from dotenv import load_dotenv

DEFAULT_MODEL = "llama3.2:3b-instruct-q4_K_M"

_probe = {"at": 0.0, "up": False}


def _host():
    load_dotenv()
    return os.getenv('OLLAMA_HOST', 'http://localhost:11434')


def get_agent_client():
    """
    Returns a configured OpenAI-compatible client for agents using local Ollama.
    Set LLM_MODEL in .env to try another pulled model (e.g. gemma3:4b).
    """
    base_url = _host() + '/v1'
    model = os.getenv('LLM_MODEL') or DEFAULT_MODEL
    return OpenAI(base_url=base_url, api_key='ollama'), model


def ollama_available(timeout=1.0, ttl=15.0):
    """True if the Ollama server answers. Cached briefly so a rerun doesn't probe again."""
    now = time.monotonic()
    if now - _probe["at"] < ttl:
        return _probe["up"]
    try:
        with urllib.request.urlopen(_host() + '/api/tags', timeout=timeout) as r:
            up = r.status == 200
    except Exception:
        up = False
    _probe.update(at=now, up=up)
    return up
