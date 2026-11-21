"""Build an offline gazetteer, data/<region>_places.json: named places with bounding boxes, from
OpenStreetMap. Optional: any place on Earth is also found online (geocode.py); a bundled list
just makes a region's neighbourhoods, parks and estates instant and typo-tolerant offline.

One-time build step (Overpass API); the app only reads the files. Data © OpenStreetMap
contributors, ODbL.

    python scripts/build_gazetteer.py                                  # Singapore (default)
    python scripts/build_gazetteer.py lisbon -9.25 38.68 -9.08 38.80   # region W S E N
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REGION = sys.argv[1] if len(sys.argv) > 1 else "singapore"
_W, _S, _E, _N = (map(float, sys.argv[2:6]) if len(sys.argv) >= 6
                  else (103.59, 1.15, 104.10, 1.48))
BBOX = (_S, _W, _N, _E)  # Overpass order: S, W, N, E
KINDS = {
    "place": "suburb|neighbourhood|quarter|island|islet|town|village|locality|city_block",
    "landuse": "residential|industrial|commercial|military|construction|port|reservoir|forest",
    "leisure": "park|nature_reserve|golf_course|stadium",
    "aeroway": "aerodrome",
    "natural": "water|wood|wetland",
    "boundary": "protected_area",
}
QUERY = "[out:json][timeout:180];(" + "".join(
    f'nwr["{k}"~"^({v})$"]["name"]({",".join(map(str, BBOX))});' for k, v in KINDS.items()
) + ");out tags bb center;"


def main() -> None:
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": QUERY}).encode(),
        headers={"User-Agent": "geoask-gazetteer/0.3 (open-source research tool)"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        els = json.load(r)["elements"]
    places: dict[str, dict] = {}
    for e in els:
        t = e.get("tags", {})
        name = t.get("name:en") or t.get("name")
        kind = next((f"{k}={t[k]}" for k in KINDS if k in t), "")
        if "bounds" in e:
            b = e["bounds"]
            bbox = [b["minlon"], b["minlat"], b["maxlon"], b["maxlat"]]
        elif "lat" in e:  # a point place: box sized by place type (half-width in degrees)
            d = {"suburb": 0.018, "town": 0.02, "quarter": 0.009, "village": 0.008,
                 "neighbourhood": 0.008}.get(t.get("place", ""), 0.0055)
            bbox = [e["lon"] - d, e["lat"] - d, e["lon"] + d, e["lat"] + d]
        else:
            continue
        bbox = [round(v, 5) for v in bbox]
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if area < 2e-6:  # < ~2 ha: too small to analyse at 10 m
            continue
        key = name.lower()
        # keep the largest feature for duplicate names (e.g. a park and its pond)
        if key not in places or area > places[key]["_a"]:
            places[key] = {"name": name, "kind": kind, "bbox": bbox, "_a": area}
    out = sorted(({k: v for k, v in p.items() if k != "_a"} for p in places.values()),
                 key=lambda p: p["name"].lower())
    path = Path(__file__).resolve().parents[1] / "data" / f"{REGION}_places.json"
    path.write_text(json.dumps({"source": "© OpenStreetMap contributors (ODbL)",
                                "places": out}, separators=(",", ":")))
    print(f"{len(out)} places → {path} ({path.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
