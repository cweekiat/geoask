"""The one-chat agent with a scripted fake model (no API key, no network)."""

import json
from pathlib import Path

from geoask.agent import chat
from geoask.agent.providers import AnthropicProvider, OllamaProvider, OpenAICompatProvider, Turn
from geoask.geolocate import images


class FakeProvider:
    kind, label, model, vision, tools = "fake", "Fake model", "fake-1", True, True

    def __init__(self, turns):
        self.turns, self.seen = list(turns), []

    def chat(self, system, messages, tools):
        self.seen.append(json.loads(json.dumps(messages, default=str)))
        return self.turns.pop(0)


def _photo():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (90, 120, 150)).save(buf, "JPEG")
    return images.load(buf.getvalue(), 1, "p.jpg")


EST = {"summary": "Central Lisbon", "clues": [{"kind": "language", "text": "Portuguese signs", "strength": "strong"}],
       "areas": [{"label": "Baixa", "lat": 38.71, "lon": -9.137, "radius_km": 1, "confidence": 0.6,
                  "level": "neighbourhood", "why": "arch"}]}


def test_tools_run_estimate_shown_and_numbers_checked(monkeypatch, tmp_path):
    monkeypatch.setattr(chat.geo, "run_tool", lambda name, args, emit: '{"found": "Rua Augusta, 38.7"}')
    fake = FakeProvider([
        Turn(text="Checking the street.", tool_calls=[{"id": "a", "name": "find_place", "args": {"query": "Rua Augusta"}}],
             stop="tool_use", thinking=["Portuguese signs."]),
        Turn(tool_calls=[{"id": "b", "name": "submit_location", "args": EST}], stop="tool_use"),
        Turn(text="Most likely the Baixa in Lisbon, about 60% sure; 999 tourists agree."),
    ])
    events = []
    chat.run_turn(fake, "s1", "Where is this?", [_photo()], None, tmp_path, events.append)
    kinds = [e["type"] for e in events]
    assert {"thinking", "note", "step", "estimate", "answer", "usage"} <= set(kinds)
    est = next(e for e in events if e["type"] == "estimate")["estimate"]
    assert est["areas"][0]["label"] == "Baixa" and est["areas"][0]["band"] == "Likely"
    ans = next(e for e in events if e["type"] == "answer")
    assert ans["unverified"] == ["999"]  # not in any tool result or user text
    # the photo reached the model; the tool result went back matched by id
    first = fake.seen[0][0]["content"]
    assert any(p["type"] == "image" for p in first)
    assert fake.seen[1][-1]["role"] == "tool_results" and fake.seen[1][-1]["results"][0]["id"] == "a"


def test_follow_up_clues_continue_the_same_conversation(monkeypatch, tmp_path):
    fake = FakeProvider([Turn(text="Somewhere in Portugal."), Turn(text="Then Lisbon is likelier.")])
    chat.run_turn(fake, "s2", "Where?", [_photo()], None, tmp_path, lambda e: None)
    chat.run_turn(fake, "s2", "The sign says Rua Augusta", [], None, tmp_path, lambda e: None)
    second = fake.seen[1]
    assert len(second) == 3 and "Rua Augusta" in json.dumps(second[-1])  # history + new clue


def test_analysis_tool_errors_go_back_to_the_model(tmp_path):
    fake = FakeProvider([
        Turn(tool_calls=[{"id": "x", "name": "terrain", "args": {}}], stop="tool_use"),
        Turn(text="Please name a place or draw a box."),
    ])
    events = []
    chat.run_turn(fake, "s3", "How steep is it here?", [], None, tmp_path, events.append)
    res = fake.seen[1][-1]["results"][0]
    assert res["is_error"] and "draw a box" in res["content"][0]["text"]


def test_wire_formats_for_each_provider():
    msgs = [{"role": "user", "content": [{"type": "text", "text": "hi"}, {"type": "image", "b64": "AAAA"}]},
            {"role": "assistant", "text": "", "tool_calls": [{"id": "c1", "name": "terrain", "args": {"place": "Zermatt"}}]},
            {"role": "tool_results", "results": [{"id": "c1", "name": "terrain",
                                                  "content": [{"type": "text", "text": "1437 m"}, {"type": "image", "b64": "BBBB"}]}]}]
    a = AnthropicProvider(client=object())._wire(msgs)
    assert a[1]["content"][0]["type"] == "tool_use" and a[2]["content"][0]["tool_use_id"] == "c1"
    o = OllamaProvider("m", capabilities=["tools", "vision"])._wire("sys", msgs)
    assert o[1]["images"] == ["AAAA"] and o[3]["role"] == "tool" and o[4]["images"] == ["BBBB"]
    no_vision = OllamaProvider("m", capabilities=["tools"])._wire("sys", msgs)
    assert "images" not in no_vision[1]
    oa = OpenAICompatProvider("m", "http://x/v1")._wire("sys", msgs)
    assert oa[2]["tool_calls"][0]["function"]["arguments"] == '{"place": "Zermatt"}'
    assert oa[3] == {"role": "tool", "tool_call_id": "c1", "content": "1437 m"}


def test_settings_round_trip(tmp_path, monkeypatch):
    from geoask import settings

    monkeypatch.setenv("GEOASK_ENV_FILE", str(tmp_path / ".env"))
    s = settings.save({"provider": "ollama", "ollama": {"model": "gemma3:12b", "bogus": 1}, "nope": 2})
    assert s["provider"] == "ollama" and s["ollama"]["model"] == "gemma3:12b" and "bogus" not in s["ollama"]
    assert "nope" not in settings.load()
    assert Path(settings.path()).name == ".geoask.json"


def test_text_form_tool_calls_from_small_models_are_recovered():
    from geoask.agent.providers import text_tool_calls

    names = {"terrain", "find_place"}
    assert text_tool_calls('terrain {"place": "Zermatt", "use_selection": false}', names)[0]["args"]["place"] == "Zermatt"
    assert text_tool_calls('<tool_call>{"name": "find_place", "arguments": {"query": "Lagos"}}</tool_call>', names)[0]["name"] == "find_place"
    assert text_tool_calls("Zermatt is steep.", names) == []
    assert text_tool_calls('delete_all {"x": 1}', names) == []  # unknown tools are never invented
