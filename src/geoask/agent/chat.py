"""One chat, one model, every tool.

The model (Claude, an Ollama model, or any OpenAI-compatible model chosen in Settings) talks with
the user and calls GeoAsk's tools: change over time, vessel activity, terrain, viewshed, line of
sight, sharpening, generative enhancement, and the geolocation tools for photos. Conversations
are kept per session, so a follow-up ("the sign says Hall Lane", another photo) refines earlier
answers, including a geolocation estimate.

Numbers: tools compute them. The model's final text is checked, and any number not found in a
tool result or in what the user wrote is flagged in the app.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from .. import aoi
from ..geolocate import agent as geo
from ..geolocate.images import Photo
from . import answer
from .planner import TOPICS, window_label, windows
from .providers import ProviderError

Emit = Callable[[dict], None]
MAX_ROUNDS = 14

SYSTEM = """You are GeoAsk, a geospatial analyst in a map app. You answer questions about any \
place on Earth by calling tools that measure open satellite, radar and elevation data, and you \
work out where photos were taken.

Ground rules:
- Numbers come only from tools. Never estimate a measurement yourself; call the tool. Quote \
figures exactly as the tool gives them; don't compute new ones (no percentages of your own, no \
rounding), because the app checks every number you write against the tool results.
- Keep replies short: two or three sentences, plain words. The app already shows each tool's \
result card on the map, so don't repeat every figure.
- Before each tool call, say in at most 12 words what you are checking.
- If the user means "here" or "this area" and has drawn a box, use use_selection. If no place \
can be determined, ask the user to name one or draw a box.
- Never identify people or help find where a private person lives or is; areas only.

Locating photos (when the user shares photos or asks where something is):
- Read every clue: scripts and languages, driving side, road markings, bollards, poles, plates \
(format only), architecture, vegetation, soil, terrain, sun and shadows; for aerial images, \
street pattern, field shapes and landmarks.
- Check specific ideas with find_place, search_map, nearby_photos, view_satellite, terrain_at \
and sun_check rather than memory.
- Then call submit_location with up to three areas and honest confidences (the probability the \
place is inside each area). Prefer a wider area you trust over a narrow guess.
- When the user adds clues or photos later, reconsider and call submit_location again with the \
updated, usually tighter, estimate. Say briefly what changed.
- Keep submit_location short: summary under 12 words, each `why` under 20 words, clues under 8."""

_PLACE = {
    "place": {"type": "string", "description": "Place name anywhere in the world."},
    "use_selection": {"type": "boolean", "description": "True to use the box the user drew."},
}

ANALYSIS_TOOLS = [
    {"name": "measure_change", "description": "Measure how an area changed between two years from "
     "Sentinel-2. topic: vegetation, water (coastline, reclamation, floods), built-up, or any "
     "(open questions like 'what changed / what is being built', uses the Clay foundation model).",
     "input_schema": {"type": "object", "properties": {
         "topic": {"type": "string", "enum": ["vegetation", "water", "built-up", "any"]}, **_PLACE,
         "start_year": {"type": "integer"}, "end_year": {"type": "integer", "description": "Omit for now"}},
         "required": ["topic"], "additionalProperties": False}},
    {"name": "vessel_activity", "description": "Pattern of life at sea: vessels on every Sentinel-1 "
     "radar pass over a port, bay or strait, with unusual days flagged.",
     "input_schema": {"type": "object", "properties": {
         **_PLACE, "since": {"type": "string", "description": "YYYY-MM or YYYY; default last 12 months"},
         "until": {"type": "string", "description": "YYYY-MM-DD, default today"}},
         "additionalProperties": False}},
    {"name": "terrain", "description": "Elevation, slope and relief of an area (Copernicus 30 m).",
     "input_schema": {"type": "object", "properties": {**_PLACE}, "additionalProperties": False}},
    {"name": "viewshed", "description": "What ground can be seen from a point, up to 15 km.",
     "input_schema": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"}, "radius_km": {"type": "number"},
         "observer_height_m": {"type": "number"}}, "required": ["lat", "lon"], "additionalProperties": False}},
    {"name": "line_of_sight", "description": "Whether point B can be seen from point A, and the "
     "first obstruction.",
     "input_schema": {"type": "object", "properties": {
         "from_lat": {"type": "number"}, "from_lon": {"type": "number"},
         "to_lat": {"type": "number"}, "to_lon": {"type": "number"},
         "observer_height_m": {"type": "number"}, "target_height_m": {"type": "number"}},
         "required": ["from_lat", "from_lon", "to_lat", "to_lon"], "additionalProperties": False}},
    {"name": "sharpen_image", "description": "Show a sharper (2.5 m, super-resolved) satellite view "
     "of an area, for viewing only.",
     "input_schema": {"type": "object", "properties": {**_PLACE, "year": {"type": "integer"}},
                      "additionalProperties": False}},
    {"name": "enhance_photo", "description": "Generate a sharper version of one of the user's "
     "photos with a generative model (invents plausible detail; for viewing, never evidence).",
     "input_schema": {"type": "object", "properties": {
         "photo": {"type": "integer", "description": "1-based photo number"},
         "guidance": {"type": "string", "description": "Optional text describing the scene"}},
         "required": ["photo"], "additionalProperties": False}},
]
GEO_TOOLS = [t for t in geo.TOOLS if t["name"] != "submit_estimate"]
SUBMIT = dict(next(t for t in geo.TOOLS if t["name"] == "submit_estimate"), name="submit_location",
              description="Submit or update the location estimate for the user's photos.")
TOOLS = ANALYSIS_TOOLS + GEO_TOOLS + [SUBMIT]


# ---- sessions ---------------------------------------------------------------------------------

_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def session(sid: str | None) -> tuple[str, dict]:
    with _lock:
        if sid and sid in _sessions:
            s = _sessions[sid]
        else:
            sid = sid if sid and sid.isalnum() and len(sid) <= 32 else uuid.uuid4().hex[:16]
            s = _sessions[sid] = {"messages": [], "photos": [], "sources": [], "t": time.time()}
            for old in sorted(_sessions, key=lambda k: _sessions[k]["t"])[:-50]:  # keep 50
                _sessions.pop(old, None)
        s["t"] = time.time()
        return sid, s


# ---- running the analysis tools ---------------------------------------------------------------

class ToolInputError(ValueError):
    pass


def _area(args: dict, selection) -> aoi.Place:
    if args.get("use_selection") or (not args.get("place") and selection):
        if not selection:
            raise ToolInputError("No box is drawn. Ask the user to draw one or name a place.")
        return aoi.from_bbox(tuple(selection))
    if args.get("place"):
        try:
            return aoi.resolve(str(args["place"]))
        except KeyError as e:
            raise ToolInputError(str(e).strip("'\"")) from e
    raise ToolInputError("Name a place or ask the user to draw a box.")


def _bbox_args(pl: aoi.Place) -> dict:
    return {"place": None if pl.source == "drawn" else pl.name, "bbox": list(pl.bbox)}


def run_analysis(name: str, args: dict, selection, out_root: Path, step: Emit,
                 photos: list[Photo] | None = None, today: date | None = None) -> dict:
    """Run one analysis tool. Returns the result dict (also used for the app's card)."""
    from ..tools import activity, investigate, superres, terrain
    from ..tools.embedding_change import embedding_change

    today = today or date.today()
    if name == "measure_change":
        pl = _area(args, selection)
        topic = str(args.get("topic", "any"))
        sy, ey = args.get("start_year"), args.get("end_year")
        t0, t1 = windows(int(sy) if sy else None, int(ey) if ey else None, today)
        kind = "embedding_change" if topic == "any" else "index_change"
        aoi.check_size(pl, kind)
        step({"type": "step", "text": f"{'Any change' if kind == 'embedding_change' else topic.title() + ' change'}"
              f" over {aoi.label(pl)}: {window_label(t0, today)} vs {window_label(t1, today)}"})
        a = _bbox_args(pl)
        if kind == "embedding_change":
            return embedding_change(a["place"], t0, t1, out_root, model="clay-v1.5",
                                    progress=lambda m: step({"type": "step", "text": m}), bbox=pl.bbox)
        return investigate.index_change(a["place"], TOPICS[topic], t0, t1, out_root,
                                        progress=lambda m: step({"type": "step", "text": m}), bbox=pl.bbox)
    if name == "vessel_activity":
        pl = _area(args, selection)
        aoi.check_size(pl, "activity")
        since = str(args.get("since") or "")
        start = (f"{since}-01" if len(since) == 7 else f"{since}-01-01" if len(since) == 4 else
                 date.fromordinal(today.toordinal() - 365).isoformat())
        until = str(args.get("until") or today.isoformat())
        return activity.activity(_bbox_args(pl)["place"], f"{start}/{until}", out_root,
                                 progress=lambda m: step({"type": "step", "text": m}), bbox=pl.bbox)
    if name == "terrain":
        pl = _area(args, selection)
        return terrain.terrain(_bbox_args(pl)["place"], out_root,
                               progress=lambda m: step({"type": "step", "text": m}), bbox=pl.bbox)
    if name == "viewshed":
        r = float(args.get("radius_km") or 5) * 1000
        h = float(args.get("observer_height_m") or 2)
        return terrain.viewshed(float(args["lon"]), float(args["lat"]), out_root, r, h, 2.0,
                                progress=lambda m: step({"type": "step", "text": m}))
    if name == "line_of_sight":
        res = terrain.line_of_sight((float(args["from_lon"]), float(args["from_lat"])),
                                    (float(args["to_lon"]), float(args["to_lat"])),
                                    float(args.get("observer_height_m") or 2), float(args.get("target_height_m") or 2))
        return res
    if name == "sharpen_image":
        pl = _area(args, selection)
        aoi.check_size(pl, "super_resolve")
        y = args.get("year")
        win = f"{int(y)}-01-01/{int(y)}-12-31" if y else windows(None, None, today)[1]
        return superres.super_resolve(_bbox_args(pl)["place"], win, out_root,
                                      progress=lambda m: step({"type": "step", "text": m}), bbox=pl.bbox)
    if name == "enhance_photo":
        from ..models import enhance

        idx = int(args.get("photo") or 1)
        if not photos or not 1 <= idx <= len(photos):
            raise ToolInputError("There's no photo with that number in this conversation.")
        return enhance.enhance_photo(photos[idx - 1], str(args.get("guidance") or ""), out_root,
                                     progress=lambda m: step({"type": "step", "text": m}))
    raise ToolInputError(f"unknown tool {name}")


def model_facts(r: dict) -> str:
    """What the model reads back from an analysis tool: the measured facts, compactly."""
    t = r.get("tool")
    if t in ("index_change", "embedding_change", "terrain", "viewshed", "super_resolve", "activity"):
        lines = answer.facts(r)
    elif t == "line_of_sight":
        ob = r.get("first_obstruction")
        lines = [f"Visible: {'yes' if r['visible'] else 'no'}", f"Distance: {r['distance_m']:.0f} m"]
        if ob:
            lines.append(f"First obstruction at {ob['distance_m']:.0f} m, {ob['above_sightline_m']:.0f} m above the sight line")
    elif t == "enhance":
        lines = [f"Enhanced photo shown to the user ({r['scale']}x, {r['model']}). Generated detail, not evidence."]
    else:
        lines = [json.dumps({k: v for k, v in r.items() if isinstance(v, (int, float, str))})[:800]]
    return "\n".join(lines) + "\nThe app shows the user a card and map layer for this result."


# ---- the turn ---------------------------------------------------------------------------------

def run_turn(provider, sid: str, text: str, new_photos: list[Photo], selection, out_root: Path,
             emit: Emit, share_meta: bool = True, base_url: str = "/outputs/") -> None:
    sid, s = session(sid)
    photos = s["photos"]
    parts: list[dict] = []
    for p in new_photos:
        p.index = len(photos) + 1
        photos.append(p)
        parts.append({"type": "text", "text": f"Photo {p.index}:"})
        parts.append({"type": "image", "b64": p.jpeg_b64})
        if p.meta and share_meta:
            parts.append({"type": "text", "text": f"Photo {p.index} metadata (read locally): {json.dumps(p.meta)}"})
    ctx = [f"Today is {date.today().isoformat()}."]
    if selection:
        w, so, e, n = selection
        ctx.append(f"The user has drawn a box: west {w:.5f}, south {so:.5f}, east {e:.5f}, north {n:.5f}.")
    parts.append({"type": "text", "text": (text or "Where were these photos taken?") + "\n\n(" + " ".join(ctx) + ")"})
    if new_photos and not provider.vision:
        emit({"type": "note", "text": f"{provider.label} can't see images, so the photos are only "
              "described by their metadata. Choose a vision model in Settings for photo geolocation."})
    s["messages"].append({"role": "user", "content": parts})
    s["sources"].append(text or "")
    for p in new_photos:
        s["sources"].append(json.dumps(p.meta))
    usage_total = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    pool = ThreadPoolExecutor(4)
    try:
        for rnd in range(1, MAX_ROUNDS + 2):
            t = provider.chat(SYSTEM, s["messages"], TOOLS if provider.tools else [])
            for k in ("input_tokens", "output_tokens", "cost_usd"):
                usage_total[k] += t.usage.get(k, 0) or 0
            usage_total["input_tokens"] += (t.usage.get("cache_read_input_tokens", 0)
                                            + t.usage.get("cache_creation_input_tokens", 0))
            emit({"type": "usage", "model": t.model or provider.label, "tokens": usage_total,
                  "cost_usd": round(usage_total["cost_usd"], 4)})
            for th in t.thinking:
                emit({"type": "thinking", "text": th})
            if t.stop == "refusal":
                raise ProviderError("The model declined this request." + (f" {t.refusal}" if t.refusal else ""))
            if t.stop == "max_tokens":
                raise ProviderError("The reply ran too long. Try a narrower question.")
            s["messages"].append({"role": "assistant", "text": t.text, "tool_calls": t.tool_calls,
                                  "raw": t.raw, "provider": provider.kind})
            if not t.tool_calls:
                bad = answer.numbers_ok(t.text, s["sources"])[1] if t.text else []
                emit({"type": "answer", "text": t.text or "Done.", "source": provider.label,
                      "unverified": bad})
                return
            if t.text:
                emit({"type": "note", "text": t.text})
            results = []

            def run(c, turn=t, rnd_=rnd):
                name, args = c["name"], c["args"] or {}
                try:
                    if name == "submit_location":
                        est = geo.validate_estimate(args)
                        est.update(model=turn.model or provider.label, rounds=rnd_,
                                   cost_usd=round(usage_total["cost_usd"], 4), usage=usage_total)
                        emit({"type": "estimate", "estimate": est})
                        s["sources"].append(" ".join(  # the figures the app displays for the estimate
                            f"{round(a['confidence'] * 100)}% {a['radius_km']} {a['lat']} {a['lon']}"
                            for a in est["areas"]) + (f" {round(est['country']['confidence'] * 100)}%"
                                                      if est.get("country") else ""))
                        return {"id": c["id"], "name": name, "content": [{"type": "text", "text": "Shown to the user."}]}
                    if any(t_["name"] == name for t_ in GEO_TOOLS):
                        emit({"type": "step", "tool": name, "text": geo.describe(name, args)})
                        out = geo.run_tool(name, args, emit)
                        content = [{"type": "text", "text": out}] if isinstance(out, str) else [
                            {"type": "text", "text": b["text"]} if b["type"] == "text" else
                            {"type": "image", "b64": b["source"]["data"]} for b in out]
                    else:
                        r = run_analysis(name, args, selection, out_root, emit, photos)
                        if r.get("id"):
                            r["base"] = f"{base_url}{r['id']}/"
                        emit({"type": "result", "result": r})
                        content = [{"type": "text", "text": model_facts(r)}]
                    s["sources"].append(" ".join(p["text"] for p in content if p["type"] == "text"))
                    return {"id": c["id"], "name": name, "content": content}
                except Exception as e:  # noqa: BLE001 - every tool failure goes back to the model
                    msg = str(e) or type(e).__name__
                    emit({"type": "step", "text": f"{name}: {msg[:120]}", "error": True})
                    return {"id": c["id"], "name": name, "is_error": True,
                            "content": [{"type": "text", "text": f"Error: {msg}"}]}

            # Fast lookups run in parallel; heavy analyses (satellite reads, models) one at a time.
            light = [c for c in t.tool_calls if c["name"] in {g["name"] for g in GEO_TOOLS} | {"submit_location"}]
            heavy = [c for c in t.tool_calls if c not in light]
            by_id = {r["id"]: r for r in list(pool.map(run, light)) + [run(c) for c in heavy]}
            results = [by_id[c["id"]] for c in t.tool_calls]
            msg = {"role": "tool_results", "results": results}
            if rnd >= MAX_ROUNDS - 1:
                msg["note"] = "Tool budget nearly used up: answer now."
            s["messages"].append(msg)
        emit({"type": "answer", "text": "I ran out of steps before finishing. Try a narrower question.",
              "source": provider.label, "unverified": []})
    finally:
        pool.shutdown(wait=False)


def run_without_model(sid: str, text: str, selection, out_root: Path, emit: Emit,
                      base_url: str = "/outputs/") -> None:
    """No model configured: the rule-based planner picks one tool; the answer is a template."""
    from .planner import Clarify, Plan, Reply, RuleBasedPlanner

    out = RuleBasedPlanner().plan(text, selection=tuple(selection) if selection else None)
    if isinstance(out, (Clarify, Reply)):
        emit({"type": "answer", "text": out.message, "source": "rule-based", "unverified": []})
        if isinstance(out, Clarify) and out.bbox:
            emit({"type": "fly", "bbox": out.bbox})
        return
    assert isinstance(out, Plan)
    emit({"type": "step", "text": out.explanation})
    from ..server import _run

    for kind, payload in _run(out.tool, out.args):
        if kind == "step":
            emit({"type": "step", "text": payload})
        else:
            payload["base"] = f"{base_url}{payload['id']}/"
            emit({"type": "result", "result": payload})
            emit({"type": "answer", "text": answer.template_answer(payload), "source": "rule-based (no model)",
                  "unverified": []})
