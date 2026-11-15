"""
Local LLM access through Ollama. The chat agents use Ollama's native /api/chat, because its OpenAI compatible endpoint
ignores the context size: with the server default, a long prompt is cut from the front without any error, and the
first turns, where the Pokemon are usually named, are what get lost. Here every call sets its context and reply length.
"""
import json
import os
import time
import urllib.request

from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_MODEL = "llama3.2:3b-instruct-q4_K_M"
# Every chat prompt fits in 4096 tokens with room for the reply; the same size on every call avoids model reloads
NUM_CTX = 4096
KEEP_ALIVE = "30m"
# Llama 3.2 runs about 3.3 characters per token on these prompts; a little under that so the estimate errs high
CHARS_PER_TOKEN = 3.0

_probe = {"at": 0.0, "up": False}


def _host():
    load_dotenv()
    host = os.getenv('OLLAMA_HOST', 'http://127.0.0.1:11434')
    # On Windows "localhost" tries IPv6 first and urllib waits about 2 s before falling back; Ollama listens on IPv4
    return host.replace("://localhost", "://127.0.0.1")


def model_name():
    """The chat model. Set LLM_MODEL in .env to try another pulled model (e.g. gemma3:4b)."""
    load_dotenv()
    return os.getenv('LLM_MODEL') or DEFAULT_MODEL


def get_agent_client():
    """An OpenAI compatible client for local Ollama, for the benchmark and offline build scripts."""
    return OpenAI(base_url=_host() + '/v1', api_key='ollama'), model_name()


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


def estimate_tokens(messages):
    return int(sum(len(m.get("content") or "") for m in messages) / CHARS_PER_TOKEN) + 8 * len(messages)


def fit(messages, max_tokens, num_ctx=NUM_CTX):
    """Drops the oldest turns between the system prompt and the last message until prompt plus reply fit the context.
    The system prompt and the question are never dropped."""
    messages = list(messages)
    while len(messages) > 2 and estimate_tokens(messages) + max_tokens > num_ctx:
        del messages[1]
    return messages


def chat(messages, temperature=0.0, max_tokens=300, stream=False, model=None, num_ctx=NUM_CTX):
    """One chat completion from Ollama: the reply text, or with stream=True a generator of text pieces."""
    body = {
        "model": model or model_name(),
        "messages": fit(messages, max_tokens, num_ctx),
        "stream": stream,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_ctx": num_ctx, "num_predict": max_tokens, "temperature": temperature},
    }
    request = urllib.request.Request(_host() + "/api/chat", json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
    if not stream:
        with urllib.request.urlopen(request, timeout=300) as r:
            return (json.load(r).get("message", {}).get("content") or "").strip()
    return _pieces(request)


def _pieces(request):
    with urllib.request.urlopen(request, timeout=300) as r:
        for line in r:
            if not line.strip():
                continue
            part = json.loads(line)
            text = part.get("message", {}).get("content")
            if text:
                yield text
            if part.get("done"):
                return
