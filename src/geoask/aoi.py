"""Areas of interest: any Singapore place name, or a box drawn on the map.

Resolution order: curated analysis areas (hand-sized to cover each development) → exact
OpenStreetMap names from the bundled gazetteer (``data/sg_places.json``, built by
``scripts/build_gazetteer.py``) → fuzzy matches, for typos.
"""

from __future__ import annotations

import difflib
import json
import math
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

BBox = tuple[float, float, float, float]  # west, south, east, north (EPSG:4326)

SINGAPORE: BBox = (103.59, 1.15, 104.10, 1.48)
SINGAPORE_UTM = "EPSG:32648"  # WGS84 / UTM 48N
MAX_KM2 = {"index_change": 250.0, "embedding_change": 80.0}  # keep answers interactive

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
    source: str = "curated"  # curated | osm | drawn

    @property
    def area_km2(self) -> float:
        return area_km2(self.bbox)


@cache
def gazetteer() -> dict[str, dict]:
    for p in (Path(__file__).resolve().parents[2] / "data" / "sg_places.json",):
        if p.exists():
            raw = json.loads(p.read_text())
            break
    else:
        try:
            raw = json.loads(resources.files("geoask").joinpath("_data/sg_places.json").read_text())
        except (FileNotFoundError, ModuleNotFoundError):
            raw = {"places": []}
    return {p["name"].lower(): p for p in raw["places"]}


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
    if osm and osm_score >= 0.82:
        return Place(gz[osm]["name"], tuple(gz[osm]["bbox"]), True, "osm")
    raise KeyError(f"I couldn't find a place called {name!r} in Singapore. "
                   "Try another name, or draw a box on the map.")


def search(q: str, limit: int = 8) -> list[Place]:
    """Places whose name starts with / contains ``q`` (curated first), for the search box."""
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
    return out[:limit]


def from_bbox(bbox: BBox, name: str = "selected area") -> Place:
    w, s, e, n = bbox
    if not (w < e and s < n):
        raise ValueError("the drawn box is empty")
    sw, ss, se, sn = SINGAPORE
    if e < sw - 0.2 or w > se + 0.2 or n < ss - 0.2 or s > sn + 0.2:
        raise ValueError("the drawn box is outside the Singapore region")
    return Place(name, (round(w, 5), round(s, 5), round(e, 5), round(n, 5)), False, "drawn")


def place_for(place: str | None, bbox: BBox | None) -> Place:
    """A drawn box wins over a name; one of the two is required."""
    if bbox:
        return from_bbox(tuple(bbox), place or "selected area")
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
