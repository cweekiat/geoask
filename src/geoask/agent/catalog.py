"""What GeoAsk can do, for the app's tool gallery: one entry per tool, with an example question
and whether it can run on this machine right now."""

from __future__ import annotations

from pathlib import Path

MODELS = Path.home() / ".cache" / "geoask" / "models"

TOOLS = [
    {"id": "embedding_change", "title": "Any change", "icon": "sparkle", "group": "Change",
     "summary": "The Clay foundation model compares every 80 m patch between two dates, so it "
                "finds construction, clearing or new water without choosing an index.",
     "example": "What changed at the Tesla Gigafactory Berlin since 2019?", "needs": "clay"},
    {"id": "index_change", "title": "Vegetation, water, built-up", "icon": "leaf", "group": "Change",
     "summary": "Spectral indices (NDVI, MNDWI, NDBI) measured in hectares lost and gained.",
     "example": "How much vegetation did the Tesla Gigafactory Berlin lose since 2019?", "needs": None},
    {"id": "activity", "title": "Vessel activity", "icon": "ship", "group": "Pattern of life",
     "summary": "Vessels on every Sentinel-1 radar pass (day, night, through cloud), unusual "
                "days flagged, with a density map.",
     "example": "How busy is the Bay of Gibraltar with ships since August 2026?", "needs": None},
    {"id": "terrain", "title": "Terrain", "icon": "mountain", "group": "Terrain",
     "summary": "Elevation, slope and relief from the Copernicus 30 m elevation model.",
     "example": "How steep is the terrain around Zermatt?", "needs": None},
    {"id": "viewshed", "title": "Viewshed", "icon": "eye", "group": "Terrain",
     "summary": "What can be seen from a point, allowing for Earth curvature. Right-click the "
                "map for a point, or measure two points for line of sight.",
     "example": "What can a 2 m observer at 45.98365, 7.78474 see within 10 km?", "needs": None},
    {"id": "super_resolve", "title": "Sharpened view", "icon": "sharpen", "group": "Imagery",
     "summary": "Sentinel-2 sharpened from 10 m to 2.5 m (SEN2SR) for viewing, with a "
                "consistency map. Never used for measurement.",
     "example": "Show me a sharper image of the Sydney Opera House", "needs": "sen2sr"},
]

_INSTALL = {
    "clay": ("clay-v1.5-encoder.pt", "python scripts/fetch_clay.py  (5.2 GB download, 0.6 GB kept)"),
    "sen2sr": ("sen2sr-lite/model.safetensor", "geoask fetch sen2sr  (3.4 MB)"),
}


def catalog() -> list[dict]:
    out = []
    for t in TOOLS:
        need = t["needs"]
        ok = need is None or (MODELS / _INSTALL[need][0]).exists()
        out.append(t | {"available": ok, "install": None if ok else _INSTALL[need][1]})
    return out
