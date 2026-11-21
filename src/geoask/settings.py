"""App settings: which model answers, and how to reach it.

Non-secret choices live in ``.geoask.json`` next to the ``.env`` file (both git-ignored); API keys
live only in ``.env`` (owner-only permissions) and are never sent back to the browser.

    {"provider": "anthropic" | "ollama" | "openai" | "none",
     "anthropic": {"model": "claude-sonnet-5-5"},
     "ollama": {"host": "http://localhost:11434", "model": "qwen2.5vl:7b"},
     "openai": {"base_url": "http://localhost:1234/v1", "model": "…", "vision": true},
     "share_photo_details": true}
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .geolocate import keys

DEFAULTS = {
    "provider": "auto",
    "anthropic": {"model": "claude-sonnet-5-5"},
    "ollama": {"host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"), "model": ""},
    "openai": {"base_url": "http://localhost:1234/v1", "model": "", "vision": True},
    "share_photo_details": True,
}
SECRET_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

# Local models worth suggesting (Ollama names). Vision + tool use is what the full agent needs.
RECOMMENDED_OLLAMA = [
    {"name": "qwen2.5vl:7b", "size_gb": 6.0, "note": "sees photos and uses tools (best local all-rounder)"},
    {"name": "gemma3:12b", "size_gb": 8.1, "note": "sees photos; strong on clues"},
    {"name": "llama3.2-vision:11b", "size_gb": 7.8, "note": "sees photos"},
    {"name": "qwen2.5:7b", "size_gb": 4.7, "note": "tools only, no vision (no photo geolocation)"},
]


def path() -> Path:
    return keys.env_file().with_name(".geoask.json")


def load() -> dict:
    s = json.loads(json.dumps(DEFAULTS))
    try:
        saved = json.loads(path().read_text())
    except (FileNotFoundError, ValueError):
        saved = {}
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update(v)
        else:
            s[k] = v
    return s


def save(update: dict) -> dict:
    s = load()
    for k, v in update.items():
        if k not in DEFAULTS:
            continue
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update({kk: vv for kk, vv in v.items() if kk in DEFAULTS[k]})
        else:
            s[k] = v
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=2))
    return s


def secret(provider: str) -> str | None:
    keys.load_env()
    var = SECRET_VARS.get(provider)
    return os.environ.get(var) if var else None


def masked(provider: str) -> str | None:
    v = secret(provider)
    return f"{v[:7]}…{v[-4:]}" if v and len(v) > 12 else ("set" if v else None)


def save_secret(provider: str, value: str) -> None:
    var = SECRET_VARS[provider]
    _set_env_line(var, value)


def remove_secret(provider: str) -> None:
    _set_env_line(SECRET_VARS[provider], None)


def _set_env_line(var: str, value: str | None) -> None:
    f = keys.env_file()
    lines = f.read_text().splitlines() if f.exists() else ["# GeoAsk settings. Never commit this file."]
    out = [ln for ln in lines if ln.strip().split("=", 1)[0].strip() != var]
    if value is not None:
        out.append(f"{var}={value}")
    keys._write(out)
    if value is None:
        os.environ.pop(var, None)
    else:
        os.environ[var] = value


def ollama_status(host: str) -> dict:
    from .agent.providers import ProviderError, ollama_models

    try:
        return {"running": True, "models": ollama_models(host)}
    except (ProviderError, OSError, ValueError):
        return {"running": False, "models": []}


def resolve_provider(s: dict | None = None):
    """The provider to use now, or None for the no-model (rule-based) mode. 'auto' picks Claude if
    a key is set, else a running Ollama with a tool-capable model, else no model."""
    from .agent.providers import AnthropicProvider, OllamaProvider, OpenAICompatProvider

    s = s or load()
    choice = s.get("provider", "auto")
    if choice == "anthropic" or (choice == "auto" and secret("anthropic")):
        if not secret("anthropic"):
            return None
        return AnthropicProvider(s["anthropic"]["model"])
    if choice == "openai":
        o = s["openai"]
        return OpenAICompatProvider(o["model"], o["base_url"], secret("openai") or "", bool(o.get("vision", True))) \
            if o.get("model") else None
    if choice in ("ollama", "auto"):
        o = s["ollama"]
        st = ollama_status(o["host"])
        if not st["running"]:
            return None
        models = st["models"]
        pick = next((m for m in models if m["name"] == o.get("model")), None)
        if pick is None and choice == "auto":  # prefer vision + tools, then tools
            pick = next((m for m in models if {"vision", "tools"} <= set(m["capabilities"])), None) or \
                next((m for m in models if "tools" in m["capabilities"]), None)
        if pick is None:
            return None
        return OllamaProvider(pick["name"], o["host"], pick["capabilities"])
    return None
