"""Model providers: one interface for every chat model GeoAsk can use.

    Claude API          AnthropicProvider   (official SDK; adaptive thinking, caching, fallback)
    Ollama (local)      OllamaProvider      (any pulled model: offline after download)
    OpenAI-compatible   OpenAICompatProvider (LM Studio, llama.cpp server, vLLM, … for non-Claude models)

Messages are kept in a neutral form so a conversation doesn't depend on the provider:

    {"role": "user", "content": [{"type": "text", "text": …} | {"type": "image", "b64": …}]}
    {"role": "assistant", "text": …, "tool_calls": [{"id", "name", "args"}], "raw": <native>}
    {"role": "tool_results", "results": [{"id", "name", "content": [parts], "is_error"}],
     "note": optional text appended after the results}

Each provider turns that into its own wire format and returns a ``Turn``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    pass


@dataclass
class Turn:
    text: str = ""
    thinking: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    stop: str = "end"  # end | tool_use | refusal | max_tokens
    usage: dict = field(default_factory=dict)
    model: str = ""
    raw: object = None  # native assistant content, replayed unchanged (Claude thinking blocks)
    refusal: str = ""


def _text(parts: list[dict]) -> str:
    return "\n".join(p["text"] for p in parts if p.get("type") == "text")


def _images(parts: list[dict]) -> list[str]:
    return [p["b64"] for p in parts if p.get("type") == "image"]


# ---- Claude ---------------------------------------------------------------------------------------

CLAUDE_MODELS = {
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-haiku-5-5": "Claude Haiku 5.5",
}
# $ per million tokens (input, output, cache read, cache write) for the cost shown in the app.
CLAUDE_PRICES = {"claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
                 "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
                 "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125)}


class AnthropicProvider:
    kind = "anthropic"
    vision = True
    tools = True

    def __init__(self, model: str = "claude-sonnet-5-5", client=None):
        self.model = model
        self.label = CLAUDE_MODELS.get(model, model)
        self._client = client

    def client(self):
        if self._client is None:
            import anthropic

            from ..geolocate import keys

            keys.load_env()
            self._client = anthropic.Anthropic()
        return self._client

    def _wire(self, messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "user":
                blocks = []
                for p in m["content"]:
                    if p["type"] == "text":
                        blocks.append({"type": "text", "text": p["text"]})
                    else:
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type":
                                                                  p.get("media", "image/jpeg"), "data": p["b64"]}})
                out.append({"role": "user", "content": blocks})
            elif m["role"] == "assistant":
                if m.get("raw") is not None and m.get("provider") == self.kind:
                    out.append({"role": "assistant", "content": m["raw"]})
                else:
                    blocks = [{"type": "text", "text": m["text"]}] if m.get("text") else []
                    blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]}
                               for c in m.get("tool_calls", [])]
                    out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "…"}]})
            else:  # tool results
                blocks = []
                for r in m["results"]:
                    content = []
                    for p in r["content"]:
                        if p["type"] == "text":
                            content.append({"type": "text", "text": p["text"]})
                        else:
                            content.append({"type": "image", "source": {"type": "base64",
                                                                        "media_type": "image/jpeg", "data": p["b64"]}})
                    blocks.append({"type": "tool_result", "tool_use_id": r["id"], "content": content,
                                   **({"is_error": True} if r.get("is_error") else {})})
                if m.get("note"):
                    blocks.append({"type": "text", "text": m["note"]})
                out.append({"role": "user", "content": blocks})
        return out

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        import anthropic

        extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
                 if self.model in ("claude-sonnet-5-5", "claude-opus-5-5") else {})
        try:
            resp = self.client().beta.messages.create(
                model=self.model, max_tokens=16000, system=system, tools=tools,
                messages=self._wire(messages), thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": "medium"}, cache_control={"type": "ephemeral"}, **extra)
        except anthropic.AuthenticationError as e:
            raise ProviderError("The Anthropic API key was rejected. Check it in Settings.") from e
        except anthropic.RateLimitError as e:
            raise ProviderError("The Claude API is rate-limiting this key. Wait a minute and try again.") from e
        except anthropic.APIStatusError as e:
            raise ProviderError(f"The Claude API returned an error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("Couldn't reach the Claude API. Check the internet connection.") from e
        u = resp.usage
        usage = {k: getattr(u, k, 0) or 0 for k in ("input_tokens", "output_tokens",
                                                     "cache_read_input_tokens", "cache_creation_input_tokens")}
        pi, po, pr, pw = CLAUDE_PRICES.get(self.model, CLAUDE_PRICES["claude-sonnet-5-5"])
        usage["cost_usd"] = (usage["input_tokens"] * pi + usage["output_tokens"] * po
                             + usage["cache_read_input_tokens"] * pr
                             + usage["cache_creation_input_tokens"] * pw) / 1e6
        t = Turn(model=resp.model, raw=resp.content, usage=usage)
        for b in resp.content:
            if b.type == "thinking" and getattr(b, "thinking", ""):
                t.thinking.append(b.thinking)
            elif b.type == "text" and b.text.strip():
                t.text += ("\n" if t.text else "") + b.text.strip()
            elif b.type == "tool_use":
                t.tool_calls.append({"id": b.id, "name": b.name, "args": dict(b.input or {})})
        if resp.stop_reason == "refusal":
            t.stop = "refusal"
            t.refusal = getattr(getattr(resp, "stop_details", None), "explanation", None) or ""
        elif resp.stop_reason == "max_tokens":
            t.stop = "max_tokens"
        elif t.tool_calls:
            t.stop = "tool_use"
        return t


# ---- HTTP helpers for local / compatible servers ------------------------------------------------

def _post(url: str, body: dict, headers: dict | None = None, timeout: float = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        raise ProviderError(f"{url.split('/')[2]} returned {e.code}: {detail}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ProviderError(f"Couldn't reach {url.split('/')[2]} ({e}).") from e


def _get(url: str, timeout: float = 3) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def text_tool_calls(text: str, names: set[str]) -> list[dict]:
    """Small local models sometimes write a tool call as text instead of using the tool API:
    'terrain {"place": "Zermatt"}', a JSON object {"name": …, "arguments": …}, or either inside
    ```json fences or <tool_call> tags. Recover those, only for known tool names."""
    import re

    t = re.sub(r"</?tool_call>|```(?:json)?", "", text or "").strip()
    out = []
    for m in re.finditer(r"\{.*\}", t, re.DOTALL):
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("name") in names:
            args = obj.get("arguments") or obj.get("parameters") or {}
            out.append({"name": obj["name"], "args": args if isinstance(args, dict) else {}})
        break
    if not out:
        m = re.match(r"^\s*([a-z_]+)\s*(\{.*\})\s*$", t, re.DOTALL)
        if m and m.group(1) in names:
            try:
                out.append({"name": m.group(1), "args": json.loads(m.group(2))})
            except ValueError:
                pass
    for c in out:
        c["id"] = "call_" + uuid.uuid4().hex[:8]
    return out


def _fn_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in tools]


# ---- Ollama ---------------------------------------------------------------------------------------

def ollama_models(host: str) -> list[dict]:
    """Installed models with what they can do ("vision", "tools")."""
    out = []
    for m in _get(f"{host}/api/tags").get("models", []):
        try:
            caps = _post(f"{host}/api/show", {"model": m["name"]}, timeout=5).get("capabilities") or []
        except ProviderError:
            caps = []
        out.append({"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 1), "capabilities": caps})
    return out


class OllamaProvider:
    kind = "ollama"

    def __init__(self, model: str, host: str = "http://localhost:11434", capabilities: list | None = None):
        self.model, self.host = model, host.rstrip("/")
        caps = capabilities
        if caps is None:
            try:
                caps = _post(f"{self.host}/api/show", {"model": model}, timeout=5).get("capabilities") or []
            except ProviderError:
                caps = []
        self.vision, self.tools = "vision" in caps, "tools" in caps
        self.label = f"{model} (Ollama)"

    def _wire(self, system: str, messages: list[dict]) -> list[dict]:
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                msg = {"role": "user", "content": _text(m["content"])}
                if self.vision and _images(m["content"]):
                    msg["images"] = _images(m["content"])
                out.append(msg)
            elif m["role"] == "assistant":
                out.append({"role": "assistant", "content": m.get("text", ""),
                            "tool_calls": [{"function": {"name": c["name"], "arguments": c["args"]}}
                                           for c in m.get("tool_calls", [])]})
            else:
                imgs = []
                for r in m["results"]:
                    out.append({"role": "tool", "tool_name": r["name"],
                                "content": ("ERROR: " if r.get("is_error") else "") + _text(r["content"])})
                    imgs += _images(r["content"])
                if (imgs and self.vision) or m.get("note"):
                    msg = {"role": "user", "content": (m.get("note") or "") + (
                        "\n(Images returned by the tools above.)" if imgs and self.vision else "")}
                    if imgs and self.vision:
                        msg["images"] = imgs[:6]
                    out.append(msg)
        return out

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        body = {"model": self.model, "messages": self._wire(system, messages), "stream": False,
                "options": {"temperature": 0.2, "num_ctx": 16384}}
        if self.tools:
            body["tools"] = _fn_tools(tools)
        res = _post(f"{self.host}/api/chat", body)
        msg = res.get("message", {})
        t = Turn(text=(msg.get("content") or "").strip(), model=self.model,
                 usage={"input_tokens": res.get("prompt_eval_count", 0),
                        "output_tokens": res.get("eval_count", 0), "cost_usd": 0.0})
        if msg.get("thinking"):
            t.thinking.append(msg["thinking"])
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            t.tool_calls.append({"id": "call_" + uuid.uuid4().hex[:8], "name": fn.get("name", ""), "args": args})
        if not t.tool_calls and tools:
            t.tool_calls = text_tool_calls(t.text, {x["name"] for x in tools})
            if t.tool_calls:
                t.text = ""
        t.stop = "tool_use" if t.tool_calls else "end"
        return t


# ---- OpenAI-compatible (for non-Claude models served by LM Studio, llama.cpp, vLLM, …) ------------

class OpenAICompatProvider:
    kind = "openai"
    tools = True

    def __init__(self, model: str, base_url: str, api_key: str = "", vision: bool = True):
        self.model, self.base, self.key, self.vision = model, base_url.rstrip("/"), api_key, vision
        self.label = f"{model} ({self.base.split('//')[-1].split('/')[0]})"

    def _wire(self, system: str, messages: list[dict]) -> list[dict]:
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                parts = [{"type": "text", "text": _text(m["content"])}]
                if self.vision:
                    parts += [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}}
                              for b in _images(m["content"])]
                out.append({"role": "user", "content": parts})
            elif m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("text") or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": c["id"], "type": "function", "function": {
                        "name": c["name"], "arguments": json.dumps(c["args"])}} for c in m["tool_calls"]]
                out.append(msg)
            else:
                imgs = []
                for r in m["results"]:
                    out.append({"role": "tool", "tool_call_id": r["id"],
                                "content": ("ERROR: " if r.get("is_error") else "") + _text(r["content"])})
                    imgs += _images(r["content"])
                if (imgs and self.vision) or m.get("note"):
                    parts = [{"type": "text", "text": (m.get("note") or "Images returned by the tools above.")}]
                    if self.vision:
                        parts += [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}"}}
                                  for b in imgs[:6]]
                    out.append({"role": "user", "content": parts})
        return out

    def chat(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        res = _post(f"{self.base}/chat/completions", {"model": self.model, "temperature": 0.2,
                                                      "messages": self._wire(system, messages),
                                                      "tools": _fn_tools(tools)}, headers)
        ch = (res.get("choices") or [{}])[0]
        msg = ch.get("message", {})
        u = res.get("usage") or {}
        t = Turn(text=(msg.get("content") or "").strip(), model=res.get("model", self.model),
                 usage={"input_tokens": u.get("prompt_tokens", 0),
                        "output_tokens": u.get("completion_tokens", 0), "cost_usd": 0.0})
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            t.tool_calls.append({"id": c.get("id") or "call_" + uuid.uuid4().hex[:8],
                                 "name": fn.get("name", ""), "args": args})
        if not t.tool_calls and tools:
            t.tool_calls = text_tool_calls(t.text, {x["name"] for x in tools})
            if t.tool_calls:
                t.text = ""
        t.stop = ("tool_use" if t.tool_calls else "max_tokens" if ch.get("finish_reason") == "length"
                  else "end")
        return t
