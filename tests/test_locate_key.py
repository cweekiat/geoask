"""Pasting the Anthropic key into the app: checked, saved to .env (owner-only), never echoed."""

import os
import stat

import pytest
from fastapi.testclient import TestClient

from geoask.geolocate import keys

KEY = "sk-ant-api03-" + "A1b2C3d4" * 6


@pytest.fixture
def client(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# settings\nMAPILLARY_TOKEN=abc\nANTHROPIC_API_KEY=sk-ant-old\n")
    monkeypatch.setenv("GEOASK_ENV_FILE", str(env))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(keys, "verify", lambda k: None)  # no network in tests
    from geoask.server import create_app

    yield TestClient(create_app()), env
    os.environ.pop("ANTHROPIC_API_KEY", None)


def test_paste_saves_key_keeps_other_settings_and_never_echoes_it(client):
    c, env = client
    r = c.post("/api/locate/key", json={"key": f'  ANTHROPIC_API_KEY="{KEY}"  '})  # messy paste
    assert r.status_code == 200, r.text
    assert KEY not in r.text and r.json()["key"].startswith("sk-ant-") and "…" in r.json()["key"]
    text = env.read_text()
    assert f"ANTHROPIC_API_KEY={KEY}" in text and "sk-ant-old" not in text
    assert "MAPILLARY_TOKEN=abc" in text and text.count("ANTHROPIC_API_KEY") == 1
    assert stat.S_IMODE(env.stat().st_mode) == 0o600  # owner read/write only
    st = c.get("/api/locate/status").json()
    assert st["available"] and KEY not in str(st)
    assert c.delete("/api/locate/key").status_code == 200
    assert "ANTHROPIC_API_KEY" not in env.read_text() and "MAPILLARY_TOKEN=abc" in env.read_text()


def test_rejects_non_keys_bad_keys_and_other_sites(client, monkeypatch):
    c, _ = client
    assert c.post("/api/locate/key", json={"key": "hello"}).status_code == 400

    def bad(k):
        raise ValueError("Anthropic didn't accept this key.")

    monkeypatch.setattr(keys, "verify", bad)
    r = c.post("/api/locate/key", json={"key": KEY})
    assert r.status_code == 400 and "didn't accept" in r.json()["detail"]
    r = c.post("/api/locate/key", json={"key": KEY}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert c.delete("/api/locate/key", headers={"Origin": "https://evil.example"}).status_code == 403
