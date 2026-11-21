"""Areas of interest and place lookup for Singapore.

Bounding boxes here are hand-entered *approximations* (WGS84 lon/lat). They get replaced by URA
Master Plan 2019 planning-area polygons and OSM features from the bundled gazetteer (week 2).
"""

from __future__ import annotations

from dataclasses import dataclass

BBox = tuple[float, float, float, float]  # west, south, east, north (EPSG:4326)

SINGAPORE: BBox = (103.59, 1.15, 104.10, 1.48)
SINGAPORE_UTM = "EPSG:32648"  # WGS84 / UTM 48N

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


def resolve(name: str) -> Place:
    key = name.strip().lower()
    if key in PLACES:
        return Place(key, PLACES[key])
    matches = [k for k in PLACES if key in k or k in key]
    if len(matches) == 1:
        return Place(matches[0], PLACES[matches[0]])
    raise KeyError(f"unknown place {name!r}; known: {', '.join(sorted(PLACES))}")


def area_km2(bbox: BBox) -> float:
    """Rough area of a small lon/lat box near the equator."""
    import math

    w, s, e, n = bbox
    lat = math.radians((s + n) / 2)
    return (e - w) * 111.32 * math.cos(lat) * (n - s) * 110.57
