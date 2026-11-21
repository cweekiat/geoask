"""The Locate agent: Claude reasons over the photos and checks its ideas with open-data tools,
then submits up to three candidate areas with confidence.

A Messages API tool loop that runs on this computer (the tools read local data and run local
compute). Sonnet 5.5 by default, Haiku 5.5 for cheaper runs. Adaptive thinking with summaries, so
the app can show the reasoning as it happens; prompt caching across loop turns; for Sonnet, the
server-side refusal fallback.

    ANTHROPIC_API_KEY=...         in .env (repo root) or the environment
    GEOASK_LOCATE_MODEL=sonnet    or haiku
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .. import geocode
from . import sources
from .images import Photo
from .sun import solar_position

MODELS = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
# $ per million tokens: input, output, cache read, cache write (5-minute). For the cost estimate
# shown to the user; the Anthropic Console is the source of truth.
PRICES = {"claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50), "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125)}
MAX_ROUNDS = 12
LEVEL_FLOOR_KM = {"exact-landmark": 0.125, "street": 0.25, "neighbourhood": 1, "city": 5,
                  "region": 25, "country": 150}

Emit = Callable[[dict], None]


class LocateError(RuntimeError):
    pass


def load_env() -> None:
    from . import keys

    keys.load_env()


def available() -> bool:
    load_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


SYSTEM = """You are the Locate agent in GeoAsk, an open-source geospatial app. People give you one \
or more images (street-level photos, aerial or satellite views, screenshots) and you estimate \
where they were taken, the way an expert GeoGuessr player would, then check your ideas with tools.

How to work:
- Read every clue in the pixels first: scripts and languages on signs, phone numbers and domains, \
which side of the road traffic uses, road markings, bollards, poles, kerbs, number-plate formats \
(as a regional clue only), vehicles, architecture and roofs, vegetation, soil, terrain, coastline, \
sun direction and shadows, and for aerial images the street pattern, field shapes and landmarks.
- Narrow from continent to country to region to town. Keep competing hypotheses alive until the \
evidence separates them.
- Use the tools to verify specific claims rather than relying on memory: look names up with \
find_place, check that a road, shop or feature exists near a candidate with search_map, compare \
the scene with nearby_photos and view_satellite, check terrain_at for mountains or flat land, and \
use sun_check when the capture time is known. If a tool fails, say so and continue.
- Be calibrated. Confidence is your honest probability that the true location is inside that \
area. Prefer a wider area you are confident in over a narrow guess. Up to three areas, ranked; \
their confidences may sum to less than 1 (the rest means "somewhere else").
- Finish by calling submit_estimate exactly once. Pick `level` to match your evidence; very small \
areas need direct evidence such as a recognised landmark or a readable street name.

Rules:
- Never try to identify any person, and ignore faces. Don't help find where a private person lives \
or is right now; if that seems to be the goal, give only the broad region (city level or wider) \
and say why.
- Areas only, no exact addresses.
- Work in the open: before each tool call, say in one short sentence what you are checking."""

TOOLS = [
    {"name": "find_place", "description": "Look up a place name, street name or landmark in \
OpenStreetMap (worldwide). Returns up to 5 matches with coordinates and a bounding box. Add a \
city or country to disambiguate, e.g. 'Rua Augusta, Lisbon'.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"], "additionalProperties": False}},
    {"name": "search_map", "description": "Search OpenStreetMap features near a point: by name \
(case-insensitive, partial match, e.g. a street or shop name read in the photo) and/or by tag \
(e.g. 'shop=supermarket', 'brand=Pingo Doce', 'highway=motorway', 'ref=N125', 'amenity=fuel'). \
Radius up to 50 km. Use it to confirm a candidate area.",
     "input_schema": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"},
         "radius_km": {"type": "number"}, "name": {"type": "string"}, "tag": {"type": "string"}},
         "required": ["lat", "lon", "radius_km"], "additionalProperties": False}},
    {"name": "nearby_photos", "description": "Open, geotagged reference photos near a point \
(Wikimedia Commons; Panoramax street-level imagery, strong in Europe; Mapillary if configured). \
Returns the images so you can compare them with the user's photo.",
     "input_schema": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"},
         "radius_m": {"type": "integer", "description": "10 to 10000, default 1000"}},
         "required": ["lat", "lon"], "additionalProperties": False}},
    {"name": "view_satellite", "description": "A recent cloud-free Sentinel-2 image (10 m pixels) \
centred on a point, size_km across (0.5 to 40). Use it to compare coastlines, street grids, \
fields, rivers or large landmarks with the user's image.",
     "input_schema": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"}, "size_km": {"type": "number"}},
         "required": ["lat", "lon"], "additionalProperties": False}},
    {"name": "terrain_at", "description": "Elevation (Copernicus 30 m surface model) at a point \
and the highest and lowest ground within radius_km (default 5). Use it to test mountains, \
valleys or flat plains seen in the photo.",
     "input_schema": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"}, "radius_km": {"type": "number"}},
         "required": ["lat", "lon"], "additionalProperties": False}},
    {"name": "sun_check", "description": "Sun azimuth and elevation, shadow direction and \
length, at a candidate place for a UTC time (ISO 8601). Compare with the shadows in the photo.",
     "input_schema": {"type": "object", "properties": {
         "lat": {"type": "number"}, "lon": {"type": "number"}, "utc_time": {"type": "string"}},
         "required": ["lat", "lon", "utc_time"], "additionalProperties": False}},
    {"name": "submit_estimate", "description": "Submit the final answer. Call exactly once, at \
the end.",
     "input_schema": {"type": "object", "properties": {
         "summary": {"type": "string", "description": "One sentence, e.g. 'Southern Portugal, "
                     "most likely central Lisbon'."},
         "country": {"type": "object", "properties": {
             "name": {"type": "string"}, "confidence": {"type": "number"}},
             "required": ["name", "confidence"], "additionalProperties": False},
         "areas": {"type": "array", "minItems": 1, "maxItems": 3, "items": {
             "type": "object", "properties": {
                 "label": {"type": "string"},
                 "lat": {"type": "number"}, "lon": {"type": "number"},
                 "radius_km": {"type": "number"},
                 "confidence": {"type": "number", "description": "0 to 1"},
                 "level": {"type": "string", "enum": list(LEVEL_FLOOR_KM)},
                 "why": {"type": "string"}},
             "required": ["label", "lat", "lon", "radius_km", "confidence", "level", "why"],
             "additionalProperties": False}},
         "clues": {"type": "array", "items": {"type": "object", "properties": {
             "kind": {"type": "string", "description": "e.g. language, driving side, road "
                      "markings, vegetation, architecture, terrain, sun, metadata, landmark"},
             "text": {"type": "string"},
             "strength": {"type": "string", "enum": ["strong", "medium", "weak"]},
             "photo": {"type": "integer", "description": "1-based photo number, if specific"}},
             "required": ["kind", "text", "strength"], "additionalProperties": False}},
         "caveats": {"type": "string"}},
         "required": ["summary", "areas", "clues"], "additionalProperties": False}},
]


# ---- tool execution -----------------------------------------------------------------------------

def _f(x, lo, hi, name):
    try:
        v = float(x)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} must be a number") from e
    if not (lo <= v <= hi) or math.isnan(v):
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return v


def run_tool(name: str, args: dict, emit: Emit) -> list[dict] | str:
    """Execute one tool. Returns tool_result content (text or text + images)."""
    if name == "find_place":
        hits = geocode.lookup(str(args["query"])[:200], limit=5)
        return json.dumps([{"name": h["name"], "lat": round((h["bbox"][1] + h["bbox"][3]) / 2, 5),
                            "lon": round((h["bbox"][0] + h["bbox"][2]) / 2, 5), "bbox": h["bbox"],
                            "kind": h["kind"]} for h in hits]) or "[]"
    lat = _f(args.get("lat"), -90, 90, "lat")
    lon = _f(args.get("lon"), -180, 180, "lon")
    if name == "search_map":
        res = sources.search_map(lat, lon, float(args.get("radius_km", 5)), args.get("name") or None,
                                 args.get("tag") or None)
        return json.dumps(res) if res else "No matching features found in that radius."
    if name == "nearby_photos":
        r = int(args.get("radius_m") or 1000)
        found = []
        for fn, k in ((sources.commons_nearby, 3), (sources.panoramax_nearby, 2),
                      (sources.mapillary_nearby, 2)):
            try:
                found += fn(lat, lon, min(r, 10000) if fn is sources.commons_nearby else min(r, 2000), k)
            except sources.SourceError:
                continue
        content: list[dict] = []
        shown = []
        for i, p in enumerate(found[:5], 1):
            try:
                b64 = sources.fetch_thumb(p["thumb"])
            except (sources.SourceError, OSError, ValueError):
                continue
            shown.append(p)
            content.append({"type": "text", "text": f"Reference {i}: {p['source']}, '{p['title']}', "
                            f"at {p['lat']}, {p['lon']} (by {p['author']}, {p['licence']})"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": b64}})
        if shown:
            emit({"type": "evidence", "kind": "photos", "items": shown})
        return content or "No open reference photos found there. Try a larger radius or another spot."
    if name == "view_satellite":
        size = _f(args.get("size_km", 2), 0.5, 40, "size_km")
        b64 = sources.satellite_view(lat, lon, size)
        emit({"type": "evidence", "kind": "satellite", "lat": lat, "lon": lon, "size_km": size,
              "credit": sources.EOX_ATTR})
        return [{"type": "text", "text": f"Sentinel-2 cloudless view, {size:g} km across, centred "
                 f"on {lat:.5f}, {lon:.5f}; north is up. {sources.EOX_ATTR}."},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}}]
    if name == "terrain_at":
        from ..tools import terrain

        rk = _f(args.get("radius_km", 5), 0.5, 25, "radius_km")
        dlat = rk / 110.57
        dlon = rk / (111.32 * max(math.cos(math.radians(lat)), 0.01))
        from ..data.grid import grid_for

        bbox = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)
        dem = terrain.dem_on(grid_for(bbox, 90.0), bbox)
        return json.dumps({"elevation_m": terrain.elevation_at(lon, lat),
                           f"min_within_{rk:g}km_m": round(float(dem.min())),
                           f"max_within_{rk:g}km_m": round(float(dem.max())),
                           "source": "Copernicus GLO-30 (includes buildings and trees)"})
    if name == "sun_check":
        t = datetime.fromisoformat(str(args["utc_time"]).replace("Z", "+00:00"))
        return json.dumps(solar_position(lat, lon, t))
    raise ValueError(f"unknown tool {name}")


def describe(name: str, a: dict) -> str:
    """Plain-language progress line for the UI (HIG: say what is happening)."""
    at = f"{a.get('lat', 0):.3f}, {a.get('lon', 0):.3f}" if "lat" in a else ""
    return {
        "find_place": f"Looking up “{a.get('query', '')}” in OpenStreetMap",
        "search_map": "Searching map data for " + " / ".join(
            x for x in (f"“{a['name']}”" if a.get("name") else "", a.get("tag", "")) if x)
            + f" within {a.get('radius_km', 5):g} km of {at}",
        "nearby_photos": f"Comparing with open reference photos near {at}",
        "view_satellite": f"Viewing satellite imagery {a.get('size_km', 2):g} km across at {at}",
        "terrain_at": f"Checking terrain and elevation around {at}",
        "sun_check": f"Checking the sun's position at {at} for {a.get('utc_time', '')}",
    }.get(name, name)


# ---- estimate validation ------------------------------------------------------------------------

def validate_estimate(e: dict) -> dict:
    """Clamp radii to the floor for each level and normalise confidences. Raises ValueError with
    a message the model can act on."""
    areas = e.get("areas") or []
    if not 1 <= len(areas) <= 3:
        raise ValueError("areas must contain 1 to 3 entries")
    out = []
    for a in areas:
        lvl = a.get("level") if a.get("level") in LEVEL_FLOOR_KM else "region"
        out.append({
            "label": str(a.get("label", ""))[:120],
            "lat": round(_f(a.get("lat"), -90, 90, "lat"), 5),
            "lon": round(_f(a.get("lon"), -180, 180, "lon"), 5),
            "radius_km": round(max(_f(a.get("radius_km"), 0, 5000, "radius_km"), LEVEL_FLOOR_KM[lvl]), 3),
            "confidence": max(0.0, min(1.0, _f(a.get("confidence"), 0, 1, "confidence"))),
            "level": lvl, "why": str(a.get("why", ""))[:600]})
    total = sum(a["confidence"] for a in out)
    if total > 1:
        for a in out:
            a["confidence"] = a["confidence"] / total
    out.sort(key=lambda a: -a["confidence"])
    for a in out:
        a["confidence"] = round(a["confidence"], 3)
        a["band"] = "Likely" if a["confidence"] >= 0.5 else "Possible" if a["confidence"] >= 0.2 else "Unlikely"
    country = e.get("country") or {}
    return {"summary": str(e.get("summary", ""))[:300], "areas": out,
            "country": {"name": str(country.get("name", ""))[:80],
                        "confidence": round(max(0.0, min(1.0, float(country.get("confidence", 0) or 0))), 3)}
            if country else None,
            "clues": [{"kind": str(c.get("kind", ""))[:40], "text": str(c.get("text", ""))[:300],
                       "strength": c.get("strength") if c.get("strength") in ("strong", "medium", "weak") else "weak",
                       "photo": c.get("photo")} for c in (e.get("clues") or [])[:20]],
            "caveats": str(e.get("caveats", ""))[:500]}


# ---- the loop -----------------------------------------------------------------------------------

def first_message(photos: list[Photo], note: str, share_meta: bool) -> list[dict]:
    content: list[dict] = []
    for p in photos:
        content.append({"type": "text", "text": f"Photo {p.index} of {len(photos)}"
                        + (f" ({p.name})" if p.name else "") + f", {p.width}×{p.height} px:"})
        content.append(p.block())
    facts = []
    for p in photos:
        if p.meta and share_meta:
            facts.append(f"Photo {p.index}: " + json.dumps(p.meta))
    content.append({"type": "text", "text": (
        "Metadata read on the user's computer:\n" + "\n".join(facts) if facts else
        "No metadata is shared for these photos (it was absent or the user chose not to share it).")
        + (f"\n\nNote from the user: {note[:1000]}" if note.strip() else "")
        + "\n\nWhere were these taken? Work through the clues, check them with the tools, then "
          "call submit_estimate."})
    return [{"role": "user", "content": content}]


def _usage_add(total: dict, u) -> None:
    for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        total[k] = total.get(k, 0) + (getattr(u, k, 0) or 0)


def cost_usd(model: str, u: dict) -> float:
    pi, po, pr, pw = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    return round((u.get("input_tokens", 0) * pi + u.get("output_tokens", 0) * po
                  + u.get("cache_read_input_tokens", 0) * pr
                  + u.get("cache_creation_input_tokens", 0) * pw) / 1e6, 4)


def locate(photos: list[Photo], emit: Emit, note: str = "", model: str = "sonnet",
           share_meta: bool = True, client=None, max_rounds: int = MAX_ROUNDS) -> dict:
    """Run the agent. ``emit`` receives progress events; returns the validated estimate."""
    import anthropic

    load_env()
    model_id = MODELS.get(model, model)
    client = client or anthropic.Anthropic()
    messages = first_message(photos, note, share_meta)
    usage: dict = {}
    extra = ({"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
             if model_id == "claude-sonnet-5-5" else {})
    nudged = False
    pool = ThreadPoolExecutor(4)
    try:
        for rnd in range(1, max_rounds + 2):
            try:
                resp = client.beta.messages.create(
                    model=model_id, max_tokens=16000, system=SYSTEM, tools=TOOLS,
                    messages=messages, thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": "medium"}, cache_control={"type": "ephemeral"},
                    **extra)
            except anthropic.AuthenticationError as e:
                raise LocateError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in .env.") from e
            except anthropic.RateLimitError as e:
                raise LocateError("The Anthropic API is rate-limiting this key. Wait a minute and try again.") from e
            except anthropic.APIStatusError as e:
                raise LocateError(f"The Claude API returned an error ({e.status_code}): {e.message}") from e
            except anthropic.APIConnectionError as e:
                raise LocateError("Couldn't reach the Claude API. Check the internet connection.") from e
            _usage_add(usage, resp.usage)
            emit({"type": "usage", "model": resp.model, "tokens": usage,
                  "cost_usd": cost_usd(model_id, usage)})
            for b in resp.content:
                if b.type == "thinking" and getattr(b, "thinking", ""):
                    emit({"type": "thinking", "text": b.thinking})
                elif b.type == "text" and b.text.strip():
                    emit({"type": "note", "text": b.text.strip()})
            if resp.stop_reason == "refusal":
                why = getattr(getattr(resp, "stop_details", None), "explanation", None)
                raise LocateError("Claude declined to locate these images."
                                  + (f" {why}" if why else ""))
            if resp.stop_reason == "max_tokens":
                raise LocateError("The answer ran too long. Try fewer photos.")
            messages.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                if nudged:
                    raise LocateError("Claude finished without submitting an estimate.")
                nudged = True
                messages.append({"role": "user", "content": "Please call submit_estimate now with "
                                 "your best areas and honest confidences."})
                continue
            results, final = [], None
            todo = []
            for c in calls:
                if c.name == "submit_estimate":
                    try:
                        final = validate_estimate(c.input)
                        results.append({"type": "tool_result", "tool_use_id": c.id, "content": "Received."})
                    except (ValueError, TypeError) as e:
                        results.append({"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                                        "content": f"Invalid estimate: {e}. Fix it and submit again."})
                else:
                    emit({"type": "step", "tool": c.name, "text": describe(c.name, c.input)})
                    todo.append(c)

            def run(c):
                try:
                    return {"type": "tool_result", "tool_use_id": c.id,
                            "content": run_tool(c.name, c.input, emit)}
                except (sources.SourceError, geocode.GeocoderUnavailable) as e:
                    return {"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                            "content": f"Source unavailable: {e}. Try another tool."}
                except (ValueError, KeyError, TypeError) as e:
                    return {"type": "tool_result", "tool_use_id": c.id, "is_error": True,
                            "content": f"Invalid input: {e}"}

            results += list(pool.map(run, todo))
            if final is not None:
                final["model"] = resp.model
                final["usage"] = usage
                final["cost_usd"] = cost_usd(model_id, usage)
                final["rounds"] = rnd
                emit({"type": "estimate", "estimate": final})
                return final
            if rnd >= max_rounds - 1:
                results.append({"type": "text", "text": "Tool budget nearly used up: call "
                                "submit_estimate in your next turn."})
            messages.append({"role": "user", "content": results})
        raise LocateError("The agent ran out of steps before submitting an estimate.")
    finally:
        pool.shutdown(wait=False)
