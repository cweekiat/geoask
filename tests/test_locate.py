"""Locate agent: photo handling, sun maths, estimate validation and the tool loop, with a scripted
fake Claude client (no API key or network needed)."""

import base64
import io
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from geoask.geolocate import agent, images
from geoask.geolocate.sun import solar_position


def _jpeg_with_gps(lat=38.7078, lon=-9.1365) -> bytes:
    img = Image.new("RGB", (2400, 1600), (120, 160, 200))
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    gps = exif.get_ifd(0x8825)

    def dms(v):
        v = abs(v)
        d = int(v)
        m = int((v - d) * 60)
        s = round(((v - d) * 60 - m) * 60, 2)
        return (float(d), float(m), s)

    gps[1], gps[2] = ("N" if lat >= 0 else "S"), dms(lat)
    gps[3], gps[4] = ("E" if lon >= 0 else "W"), dms(lon)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_metadata_is_read_locally_and_stripped_from_what_claude_sees():
    p = images.load(_jpeg_with_gps(), 1, "lisbon.jpg")
    assert p.meta["camera"] == "TestCam"
    assert abs(p.meta["gps"]["lat"] - 38.7078) < 1e-3 and abs(p.meta["gps"]["lon"] + 9.1365) < 1e-3
    sent = Image.open(io.BytesIO(base64.b64decode(p.jpeg_b64)))
    assert not sent.getexif()  # no EXIF, so no GPS, leaves the machine
    assert max(sent.size) <= images.MAX_SIDE
    with pytest.raises(ValueError):
        images.load(b"not an image", 1)


def test_sun_position_matches_known_values():
    s = solar_position(51.5, -0.12, datetime(2026, 12, 21, 12, 0, tzinfo=timezone.utc))
    assert abs(s["elevation_deg"] - 15.1) < 0.3 and abs(s["azimuth_deg"] - 180) < 2
    s = solar_position(1.35, 103.82, datetime(2026, 6, 21, 5, 10, tzinfo=timezone.utc))
    assert s["azimuth_deg"] > 340 or s["azimuth_deg"] < 20  # June, Singapore: sun to the north


def test_estimate_validation_floors_radius_and_normalises_confidence():
    e = agent.validate_estimate({"summary": "x", "clues": [], "areas": [
        {"label": "a", "lat": 38.7, "lon": -9.1, "radius_km": 0.01, "confidence": 0.9,
         "level": "street", "why": ""},
        {"label": "b", "lat": 41.1, "lon": -8.6, "radius_km": 3, "confidence": 0.6,
         "level": "city", "why": ""}]})
    assert e["areas"][0]["radius_km"] == agent.LEVEL_FLOOR_KM["street"]  # never a pinpoint
    assert e["areas"][1]["radius_km"] == agent.LEVEL_FLOOR_KM["city"]
    assert abs(sum(a["confidence"] for a in e["areas"]) - 1) < 1e-6
    assert e["areas"][0]["band"] == "Likely"
    with pytest.raises(ValueError):
        agent.validate_estimate({"areas": []})


class FakeClient:
    """Plays back scripted assistant turns and records what the agent sent."""

    def __init__(self, turns):
        self.turns, self.sent = list(turns), []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.sent.append(kw)
        content, stop = self.turns.pop(0)
        return NS(content=content, stop_reason=stop, model=kw["model"], stop_details=None,
                  usage=NS(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                           cache_creation_input_tokens=0))


def _tool(id_, name, inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def test_agent_loop_runs_tools_then_returns_validated_areas(monkeypatch):
    monkeypatch.setattr(agent, "run_tool", lambda name, args, emit: '{"ok": true}')
    est = {"summary": "Central Lisbon", "country": {"name": "Portugal", "confidence": 0.9},
           "clues": [{"kind": "language", "text": "Portuguese signs", "strength": "strong"}],
           "areas": [{"label": "Baixa, Lisbon", "lat": 38.71, "lon": -9.137, "radius_km": 1,
                      "confidence": 0.7, "level": "neighbourhood", "why": "arch + square"}]}
    fake = FakeClient([
        ([NS(type="thinking", thinking="Portuguese signs; looks like Lisbon."),
          NS(type="text", text="Checking the street name."),
          _tool("t1", "find_place", {"query": "Rua Augusta, Lisbon"})], "tool_use"),
        ([_tool("t2", "submit_estimate", est)], "tool_use"),
    ])
    events = []
    p = images.load(_jpeg_with_gps(), 1, "x.jpg")
    out = agent.locate([p], events.append, model="sonnet", share_meta=False, client=fake)
    assert out["areas"][0]["label"] == "Baixa, Lisbon" and out["rounds"] == 2
    kinds = [e["type"] for e in events]
    assert {"thinking", "note", "step", "usage", "estimate"} <= set(kinds)
    first = fake.sent[0]
    assert first["model"] == "claude-sonnet-5-5" and first["fallbacks"] == "default"
    assert first["thinking"] == {"type": "adaptive", "display": "summarized"}
    text = " ".join(b.get("text", "") for b in first["messages"][0]["content"] if b["type"] == "text")
    assert "38.70" not in text  # share_meta=False: GPS isn't sent
    # tool results go back in one user message, matched by id
    assert fake.sent[1]["messages"][2]["content"][0]["tool_use_id"] == "t1"


def test_agent_reports_refusal_and_missing_estimate(monkeypatch):
    p = images.load(_jpeg_with_gps(), 1)
    fake = FakeClient([([], "refusal")])
    with pytest.raises(agent.LocateError, match="declined"):
        agent.locate([p], lambda e: None, model="haiku", client=fake)
    assert "fallbacks" not in fake.sent[0]  # Haiku: no server-side fallback
    fake = FakeClient([([NS(type="text", text="Probably Lisbon.")], "end_turn"),
                       ([NS(type="text", text="Lisbon.")], "end_turn")])
    with pytest.raises(agent.LocateError, match="without submitting"):
        agent.locate([p], lambda e: None, client=fake)


def test_elevation_tiles_merge_without_fake_zeros(monkeypatch):
    """A box across two 1° DEM tiles: each tile covers half; nothing should read as 0 m."""
    import numpy as np

    from geoask.data.grid import grid_for
    from geoask.tools import terrain

    seen = []

    def fake_read(url, grid, resampling, nodata=None):
        seen.append(nodata)
        a = np.full(grid.shape, np.nan, np.float32)
        half = grid.width // 2
        if "E007" in url:
            a[:, :half] = 2000.0
        else:
            a[:, half:] = 3000.0
        return a

    monkeypatch.setattr(terrain, "read_to_grid", fake_read)
    bb = (7.9, 45.9, 8.1, 46.0)
    d = terrain.dem_on(grid_for(bb, 90), bb)
    assert d.min() >= 2000 and all(v is not None for v in seen)
