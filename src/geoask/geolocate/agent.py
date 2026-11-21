"""Geolocation tools for the chat agent: clue checks against open data, and the location estimate.

The chat agent (``geoask.agent.chat``) offers these to whichever model is chosen in Settings:
find_place, search_map, nearby_photos, view_satellite, terrain_at, sun_check, and
submit_location (validated here: up to three areas, radius floors per level, normalised
confidence; never a pinpoint).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from datetime import datetime

from .. import geocode
from . import sources
from .sun import solar_position

LEVEL_FLOOR_KM = {"exact-landmark": 0.125, "street": 0.25, "neighbourhood": 1, "city": 5,
                  "region": 25, "country": 150}

Emit = Callable[[dict], None]


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
         "summary": {"type": "string", "description": "Under 12 words, e.g. 'Central Lisbon, "
                     "Portugal'."},
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
