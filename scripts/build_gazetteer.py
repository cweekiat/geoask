"""Build data/sg_places.json: named places in Singapore with bounding boxes, from OpenStreetMap.

One-time build step (Overpass API); the app itself only reads the bundled file. Data © OpenStreetMap
contributors, ODbL.

    python scripts/build_gazetteer.py
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

BBOX = (1.15, 103.59, 1.48, 104.10)  # S, W, N, E
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
    path = Path(__file__).resolve().parents[1] / "data" / "sg_places.json"
    path.write_text(json.dumps({"source": "© OpenStreetMap contributors (ODbL)",
                                "places": out}, separators=(",", ":")))
    print(f"{len(out)} places → {path} ({path.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
