"""Find any place on Earth by name, with no API key.

Uses OpenStreetMap's Nominatim (free, keyless). Its usage policy asks for at most one request a
second, an identifying User-Agent, cached results and no search-as-you-type, so:

* lookups happen only when a question is asked or Enter is pressed in the search box;
* every answer (including "not found") is cached on disk, so repeat lookups never hit the network;
* requests are spaced at least 1 s apart.

    GEOASK_GEOCODER=https://nominatim.openstreetmap.org   (or your own Nominatim / "off")
    GEOASK_USER_AGENT="geoask (contact: you@example.org)"  recommended if you run it a lot

Results © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import __version__

URL = os.environ.get("GEOASK_GEOCODER", "https://nominatim.openstreetmap.org").rstrip("/")
UA = os.environ.get("GEOASK_USER_AGENT", f"geoask/{__version__} (open-source satellite Q&A)")
CACHE = Path(os.environ.get("GEOASK_CACHE", Path.home() / ".cache" / "geoask")) / "geocode.json"
LANG = os.environ.get("GEOASK_LANG", "en")  # names in this language where OSM has them
MIN_SIDE_KM = 1.0  # a point-like result (a building, a junction) gets at least a 1 km box

_lock = threading.Lock()
_last = 0.0


class GeocoderUnavailable(RuntimeError):
    pass


def _load() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _save(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(f".{os.getpid()}.part")
    tmp.write_text(json.dumps(cache))
    tmp.replace(CACHE)


def lookup(name: str, limit: int = 5, timeout: float = 8) -> list[dict]:
    """Places matching ``name``: ``[{"name", "bbox": [w, s, e, n], "kind"}]``, best first."""
    global _last
    key = f"{LANG}|{limit}|{' '.join(name.lower().split())}"
    with _lock:
        cache = _load()
        if key in cache:
            return cache[key]
        if URL.lower() == "off":
            raise GeocoderUnavailable("the online place search is switched off")
        wait = 1.0 - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        qs = urllib.parse.urlencode({"q": name, "format": "jsonv2", "limit": limit,
                                     "accept-language": LANG})
        req = urllib.request.Request(f"{URL}/search?{qs}", headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise GeocoderUnavailable(f"the place search didn't answer ({e})") from e
        finally:
            _last = time.time()
        out = [_place(x) for x in raw if x.get("boundingbox")]
        cache[key] = out
        _save(cache)
        return out


def _place(x: dict) -> dict:
    s, n, w, e = (float(v) for v in x["boundingbox"])
    lat, lon = float(x["lat"]), float(x["lon"])
    from .aoi import area_km2  # local import: aoi imports this module

    if area_km2((w, s, e, n)) < MIN_SIDE_KM**2:
        dlat = MIN_SIDE_KM / 2 / 110.57
        dlon = MIN_SIDE_KM / 2 / (111.32 * max(math.cos(math.radians(lat)), 0.01))
        w, s, e, n = lon - dlon, lat - dlat, lon + dlon, lat + dlat
    return {"name": x.get("display_name") or x.get("name", ""),
            "short": x.get("name") or x.get("display_name", "").split(",")[0],
            "bbox": [round(w, 5), round(s, 5), round(e, 5), round(n, 5)],
            "kind": f"{x.get('category', '')}/{x.get('type', '')}"}
