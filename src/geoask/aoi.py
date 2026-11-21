"""Areas of interest: any place name on Earth, or a box drawn on the map.

Resolution order, cheapest first:

1. curated analysis areas (hand-sized to cover a whole development; the demo set is Singapore);
2. bundled offline gazetteers (``data/*_places.json``, built by ``scripts/build_gazetteer.py``
   for any region), exact names, then close matches for typos;
3. the online geocoder (``geocode.py``: OpenStreetMap Nominatim, keyless, cached on disk).
"""

from __future__ import annotations

import difflib
import json
import math
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

from . import geocode

BBox = tuple[float, float, float, float]  # west, south, east, north (EPSG:4326)

SINGAPORE: BBox = (103.59, 1.15, 104.10, 1.48)
MAX_KM2 = {"index_change": 250.0, "embedding_change": 80.0, "terrain": 2500.0,
           "super_resolve": 25.0, "activity": 400.0}  # keep answers interactive

# Curated analysis areas: sized to the whole development, not OSM's point/label box.
PLACES: dict[str, BBox] = {
    "singapore": SINGAPORE,
    "tengah": (103.715, 1.345, 103.755, 1.375),
    "tuas": (103.600, 1.220, 103.680, 1.340),
    "pulau tekong": (103.950, 1.380, 104.060, 1.430),
    "jurong island": (103.660, 1.240, 103.730, 1.300),
    "punggol": (103.890, 1.390, 103.930, 1.420),
    "changi airport": (103.970, 1.330, 104.010, 1.400),
    "marina bay": (103.850, 1.270, 103.870, 1.300),
    "central catchment": (103.780, 1.340, 103.830, 1.400),
}


@dataclass(frozen=True)
class Place:
    name: str
    bbox: BBox
    approximate: bool = True
    source: str = "curated"  # curated | osm | geocoder | drawn

    @property
    def area_km2(self) -> float:
        return area_km2(self.bbox)


@cache
def gazetteer() -> dict[str, dict]:
    """Every bundled offline gazetteer, merged (first file wins on duplicate names)."""
    src = Path(__file__).resolve().parents[2] / "data"
    files = sorted(src.glob("*_places.json")) if src.is_dir() else []
    if not files:
        try:
            pkg = resources.files("geoask").joinpath("_data")
            files = sorted(f for f in pkg.iterdir() if f.name.endswith("_places.json"))
        except (FileNotFoundError, ModuleNotFoundError):
            files = []
    out: dict[str, dict] = {}
    for f in files:
        for p in json.loads(f.read_text())["places"]:
            out.setdefault(p["name"].lower(), p)
    return out


def resolve(name: str) -> Place:
    key = " ".join(name.strip().lower().split())
    for prefix in ("the ", "pulau "):  # "the Tuas area", "Pulau Tekong" / "Tekong"
        if key.startswith(prefix) and key[len(prefix):] in PLACES:
            key = key[len(prefix):]
    if key in PLACES:
        return Place(key, PLACES[key])
    gz = gazetteer()
    if key in gz:
        return Place(gz[key]["name"], tuple(gz[key]["bbox"]), True, "osm")
    curated = [k for k in PLACES if k != "singapore" and (key in k or k in key)]
    if len(curated) == 1:
        return Place(curated[0], PLACES[curated[0]])
    def best(names) -> tuple[float, str | None]:
        scored = [(difflib.SequenceMatcher(None, key, n).ratio(), n) for n in names]
        return max(scored, default=(0.0, None))

    cur_score, cur = best(k for k in PLACES if k != "singapore")
    osm_score, osm = best(gz)
    if cur and cur_score >= 0.8 and cur_score >= osm_score - 0.05:  # typos favour curated areas
        return Place(cur, PLACES[cur])
    if osm and osm_score >= 0.9:  # near-certain typo of a bundled name: no network needed
        return Place(gz[osm]["name"], tuple(gz[osm]["bbox"]), True, "osm")
    try:
        hits = geocode.lookup(name, limit=1)
    except geocode.GeocoderUnavailable:
        hits = []
    if hits:
        h = hits[0]
        return Place(h["short"], tuple(h["bbox"]), True, "geocoder")
    if osm and osm_score >= 0.82:
        return Place(gz[osm]["name"], tuple(gz[osm]["bbox"]), True, "osm")
    raise KeyError(f"I couldn't find a place called {name!r}. "
                   "Try another name, or draw a box on the map.")


def search(q: str, limit: int = 8, online: bool = False) -> list[Place]:
    """Places whose name starts with / contains ``q`` (curated first), for the search box.
    ``online`` adds geocoder results; the app asks for that only when Enter is pressed."""
    q = q.strip().lower()
    out: list[Place] = []
    seen: set[str] = set()

    def add(p: Place) -> None:
        if p.name.lower() not in seen:
            seen.add(p.name.lower())
            out.append(p)

    for k, b in PLACES.items():
        if k != "singapore" and (not q or q in k):
            add(Place(k, b))
    gz = gazetteer()
    for k in sorted(gz, key=lambda k: (not k.startswith(q), len(k))):
        if q and q in k:
            add(Place(gz[k]["name"], tuple(gz[k]["bbox"]), True, "osm"))
        if len(out) >= limit:
            break
    if online and q:
        try:
            for h in geocode.lookup(q, limit=limit):
                add(Place(h["name"], tuple(h["bbox"]), True, "geocoder"))
        except geocode.GeocoderUnavailable:
            pass
    return out[: limit * 2 if online else limit]


def from_bbox(bbox: BBox, name: str = "selected area", source: str = "drawn") -> Place:
    w, s, e, n = bbox
    if not (w < e and s < n):
        raise ValueError("the drawn box is empty")
    if s < -84 or n > 84 or w < -180 or e > 180:
        raise ValueError("the drawn box must lie between 84° south and 84° north")
    return Place(name, (round(w, 5), round(s, 5), round(e, 5), round(n, 5)), False, source)


def place_for(place: str | None, bbox: BBox | None) -> Place:
    """A drawn box wins over a name; one of the two is required."""
    if bbox:
        # a named box (from the geocoder or a bundled list) keeps its name; a bare one was drawn
        return from_bbox(tuple(bbox), place or "selected area", "named" if place else "drawn")
    if place:
        return resolve(place)
    raise KeyError("Name a place or draw a box on the map.")


def check_size(p: Place, tool: str) -> None:
    lim = MAX_KM2.get(tool)
    if lim and p.area_km2 > lim:
        raise ValueError(f"{p.name.title()} is {p.area_km2:.0f} km², larger than the "
                         f"{lim:.0f} km² this analysis supports. Draw a smaller box.")


def area_km2(bbox: BBox) -> float:
    """Approximate area of a small lon/lat box near the equator."""
    w, s, e, n = bbox
    lat = math.radians((s + n) / 2)
    return (e - w) * 111.32 * math.cos(lat) * (n - s) * 110.57


def label(p: Place) -> str:
    """Display name: curated lower-case keys get title case; geocoded or coordinate names
    ("Lisbon", "48N UG 7199 4950") are kept as written."""
    return p.name if any(c.isupper() or c.isdigit() for c in p.name) else p.name.title()
