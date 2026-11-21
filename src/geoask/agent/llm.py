"""Minimal client for a local Ollama server (free, runs on macOS and Linux).

    GEOASK_LLM=qwen2.5:7b          model (default)
    OLLAMA_HOST=http://localhost:11434
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("GEOASK_LLM", "qwen2.5:7b")


class LLMUnavailable(RuntimeError):
    pass


def available(model: str = MODEL, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"{HOST}/api/tags", timeout=timeout) as r:
            names = {m["name"] for m in json.load(r).get("models", [])}
        return model in names
    except (urllib.error.URLError, OSError, ValueError):
        return False


def chat(messages: list[dict], tools: list[dict] | None = None, model: str = MODEL,
         timeout: float = 120, temperature: float = 0.0) -> dict:
    """One non-streaming chat turn. Returns Ollama's ``message`` dict."""
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_ctx": 4096}}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(f"{HOST}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["message"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        raise LLMUnavailable(f"Ollama at {HOST} didn't answer: {e}") from e
