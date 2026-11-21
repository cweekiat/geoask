"""The Anthropic API key for Locate: pasted once in the app, kept only on this computer.

The key is checked against the API (a free model-list call), written to the ``.env`` file with
owner-only permissions, and loaded into this process. It is never sent back to the browser: the
app only ever sees a masked form such as ``sk-ant-…a1b2``.

    GEOASK_ENV_FILE=/path/.env   overrides where it is stored
    (default: the repo's .env when running from a checkout, else ~/.config/geoask/.env)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

KEY_VAR = "ANTHROPIC_API_KEY"
_KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,300}$")


def env_file() -> Path:
    if os.environ.get("GEOASK_ENV_FILE"):
        return Path(os.environ["GEOASK_ENV_FILE"]).expanduser()
    repo = Path(__file__).resolve().parents[3]
    if (repo / "pyproject.toml").exists():
        return repo / ".env"
    return Path.home() / ".config" / "geoask" / ".env"


def load_env() -> None:
    """Read KEY=VALUE lines from the .env file into the environment (existing vars win)."""
    f = env_file()
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def current() -> str | None:
    load_env()
    return os.environ.get(KEY_VAR) or None


def masked(key: str | None = None) -> str | None:
    key = key if key is not None else current()
    return f"{key[:7]}…{key[-4:]}" if key and len(key) > 12 else None


def clean(raw: str) -> str:
    """Accept what people actually paste: surrounding spaces/quotes, or a whole
    'ANTHROPIC_API_KEY=sk-ant-…' line."""
    k = raw.strip().strip('"').strip("'")
    if "=" in k and k.split("=", 1)[0].strip().upper() == KEY_VAR:
        k = k.split("=", 1)[1].strip().strip('"').strip("'")
    return k


def looks_valid(key: str) -> bool:
    return bool(_KEY_RE.match(key))


def verify(key: str) -> None:
    """Raise ValueError with a plain message if Anthropic rejects the key."""
    import anthropic

    try:
        anthropic.Anthropic(api_key=key, max_retries=1, timeout=15).models.list(limit=1)
    except anthropic.AuthenticationError as e:
        raise ValueError("Anthropic didn't accept this key. Copy it again from the Console.") from e
    except anthropic.PermissionDeniedError as e:
        raise ValueError("This key doesn't have access to the API.") from e
    except anthropic.APIConnectionError as e:
        raise ValueError("Couldn't reach Anthropic to check the key. Check the internet connection.") from e
    except anthropic.APIStatusError as e:
        raise ValueError(f"Anthropic couldn't check the key right now ({e.status_code}). Try again.") from e


def _write(lines: list[str]) -> None:
    f = env_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f".env.{os.getpid()}.part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # owner read/write only
    with os.fdopen(fd, "w") as out:
        out.write("\n".join(lines).rstrip("\n") + "\n")
    tmp.replace(f)
    os.chmod(f, 0o600)


def save(key: str) -> None:
    """Write (or replace) the key line in .env, keeping every other line, and load it now."""
    f = env_file()
    lines = f.read_text().splitlines() if f.exists() else [
        "# GeoAsk settings. Never commit this file."]
    out, done = [], False
    for line in lines:
        if line.strip().split("=", 1)[0].strip() == KEY_VAR:
            if not done:
                out.append(f"{KEY_VAR}={key}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{KEY_VAR}={key}")
    _write(out)
    os.environ[KEY_VAR] = key


def remove() -> None:
    f = env_file()
    if f.exists():
        _write([ln for ln in f.read_text().splitlines()
                if ln.strip().split("=", 1)[0].strip() != KEY_VAR])
    os.environ.pop(KEY_VAR, None)
