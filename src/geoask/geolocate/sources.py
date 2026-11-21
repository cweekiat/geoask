"""Free, open evidence sources for the Locate agent. Keyless except Mapillary (optional token).

* OpenStreetMap Overpass: named roads, road numbers, shop brands and other features near a place.
* Wikimedia Commons: geotagged photos near a candidate, to compare with the user's photo.
* Panoramax: open street-level imagery (strongest in France and Europe).
* Mapillary: worldwide street-level imagery, only if MAPILLARY_TOKEN is set (free account).
* EOX Sentinel-2 cloudless: a recent cloud-free satellite view of a candidate area.

Every request is cached on disk (``~/.cache/geoask/locate``) and identifies GeoAsk with a generic
User-Agent. Results and images are attributed to their authors and licences.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .. import __version__

UA = os.environ.get("GEOASK_USER_AGENT", f"geoask/{__version__} (open-source satellite Q&A)")
CACHE = Path(os.environ.get("GEOASK_CACHE", Path.home() / ".cache" / "geoask")) / "locate"
OVERPASS = [u for u in os.environ.get("GEOASK_OVERPASS", "").split(",") if u] or [
    "https://overpass-api.de/api/interpreter",  # main server, often busy: mirrors follow
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


class SourceError(RuntimeError):
    pass


def _get(url: str, data: bytes | None = None, timeout: float = 25, binary: bool = False,
         ttl_days: float = 30):
    key = hashlib.sha256(url.encode() + (data or b"")).hexdigest()[:32]
    path = CACHE / (key + (".bin" if binary else ".json"))
    if path.exists() and time.time() - path.stat().st_mtime < ttl_days * 86400:
        raw = path.read_bytes()
        return raw if binary else json.loads(raw)
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except (urllib.error.URLError, OSError) as e:
        raise SourceError(f"{urllib.parse.urlparse(url).netloc} didn't answer ({e})") from e
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.part")
    tmp.write_bytes(raw)
    tmp.replace(path)
    return raw if binary else json.loads(raw)


def _box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    dlat = radius_km / 110.57
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def _jpeg_b64(raw: bytes, max_side: int = 768) -> str:
    from PIL import Image

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode()


# ---- OpenStreetMap Overpass --------------------------------------------------------------------

def search_map(lat: float, lon: float, radius_km: float, name: str | None = None,
               tag: str | None = None, limit: int = 15) -> list[dict]:
    """Features near (lat, lon) whose name matches ``name`` (case-insensitive) and/or that carry
    ``tag`` ("key=value" or "key"). Returns name, main tags and position."""
    radius_km = min(max(radius_km, 0.1), 50.0)
    if not name and not tag:
        raise ValueError("give a name, a tag, or both")
    flt = ""
    if tag:
        k, _, v = tag.partition("=")
        flt += f'["{_q(k)}"="{_q(v)}"]' if v else f'["{_q(k)}"]'
    if name:
        flt += f'["name"~"{_q(name)}",i]'
    q = (f"[out:json][timeout:25];nwr{flt}(around:{int(radius_km * 1000)},{lat},{lon});"
         f"out tags center {int(limit)};")
    body = urllib.parse.urlencode({"data": q}).encode()
    for i, url in enumerate(OVERPASS):
        try:
            res = _get(url, data=body, timeout=15)
            break
        except SourceError:
            if i == len(OVERPASS) - 1:
                raise
    keep = ("name", "highway", "ref", "amenity", "shop", "brand", "railway", "landuse", "natural",
            "tourism", "historic", "building", "place", "addr:city", "operator", "sport", "man_made")
    out = []
    for el in res.get("elements", [])[:limit]:
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        tags = el.get("tags", {})
        out.append({"lat": c.get("lat"), "lon": c.get("lon"),
                    "tags": {k: tags[k] for k in keep if k in tags},
                    "osm": f"{el['type']}/{el['id']}"})
    return out


def _q(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')[:80]


# ---- reference photos ---------------------------------------------------------------------------

def commons_nearby(lat: float, lon: float, radius_m: int = 1000, limit: int = 4) -> list[dict]:
    """Geotagged Wikimedia Commons photos near a point, with author and licence."""
    radius_m = min(max(int(radius_m), 10), 10000)
    qs = urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "geosearch", "ggsnamespace": 6,
        "ggscoord": f"{lat}|{lon}", "ggsradius": radius_m, "ggslimit": limit * 3,
        "prop": "imageinfo|coordinates", "iiprop": "url|extmetadata|mime", "iiurlwidth": 640})
    res = _get(f"https://commons.wikimedia.org/w/api.php?{qs}")
    out = []
    for page in sorted(res.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        if not str(info.get("mime", "")).startswith("image/jpeg"):
            continue
        md = info.get("extmetadata", {})
        coord = (page.get("coordinates") or [{}])[0]
        out.append({"source": "Wikimedia Commons", "title": page.get("title", "")[5:],
                    "thumb": info.get("thumburl"), "page": info.get("descriptionurl"),
                    "author": _strip_html(md.get("Artist", {}).get("value", "unknown")),
                    "licence": md.get("LicenseShortName", {}).get("value", ""),
                    "lat": coord.get("lat"), "lon": coord.get("lon")})
        if len(out) >= limit:
            break
    return out


def panoramax_nearby(lat: float, lon: float, radius_m: int = 300, limit: int = 3) -> list[dict]:
    w, s, e, n = _box(lat, lon, max(radius_m, 50) / 1000)
    qs = urllib.parse.urlencode({"bbox": f"{w},{s},{e},{n}", "limit": limit})
    res = _get(f"https://api.panoramax.xyz/api/search?{qs}")
    out = []
    for f in res.get("features", [])[:limit]:
        a = f.get("assets", {})
        thumb = (a.get("sd") or a.get("thumb") or {}).get("href")
        lo, la = (f.get("geometry") or {}).get("coordinates", [None, None])[:2]
        props = f.get("properties", {})
        out.append({"source": "Panoramax", "title": props.get("datetime", "")[:10], "thumb": thumb,
                    "page": f"https://api.panoramax.xyz/#focus=pic&pic={f.get('id')}",
                    "author": (props.get("geovisio:producer") or "Panoramax contributor"),
                    "licence": props.get("license", "CC-BY-SA-4.0"), "lat": la, "lon": lo})
    return [x for x in out if x["thumb"]]


def mapillary_nearby(lat: float, lon: float, radius_m: int = 300, limit: int = 3) -> list[dict]:
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        return []
    w, s, e, n = _box(lat, lon, max(radius_m, 50) / 1000)
    qs = urllib.parse.urlencode({"access_token": token, "fields": "id,thumb_1024_url,geometry",
                                 "bbox": f"{w},{s},{e},{n}", "limit": limit})
    res = _get(f"https://graph.mapillary.com/images?{qs}", ttl_days=7)
    return [{"source": "Mapillary", "title": d["id"], "thumb": d.get("thumb_1024_url"),
             "page": f"https://www.mapillary.com/app/?pKey={d['id']}", "author": "Mapillary contributor",
             "licence": "CC-BY-SA-4.0", "lat": d["geometry"]["coordinates"][1],
             "lon": d["geometry"]["coordinates"][0]} for d in res.get("data", [])[:limit]]


def fetch_thumb(url: str) -> str:
    return _jpeg_b64(_get(url, binary=True))


def _strip_html(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", s).strip()[:120]


# ---- satellite view -----------------------------------------------------------------------------

EOX_YEAR = 2024
EOX_ATTR = ("Sentinel-2 cloudless by EOX IT Services GmbH (contains modified Copernicus Sentinel "
            f"data {EOX_YEAR}), CC BY-NC-SA 4.0")


def satellite_view(lat: float, lon: float, size_km: float = 2.0) -> str:
    """A ~768 px cloud-free Sentinel-2 view (10 m) centred on a point, as base64 JPEG."""
    from PIL import Image

    size_km = min(max(size_km, 0.5), 40.0)
    # about 3 tiles across the view: a tile spans 40075·cos(lat) / 2^z km
    z = max(6, min(15, round(math.log2(40075 * math.cos(math.radians(lat)) * 3 / size_km))))
    n = 2 ** z

    def tile_xy(la: float, lo: float) -> tuple[float, float]:
        x = (lo + 180) / 360 * n
        y = (1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n
        return x, y

    w, s, e, nn = _box(lat, lon, size_km / 2)
    x0, y0 = tile_xy(nn, w)
    x1, y1 = tile_xy(s, e)
    tiles_x = range(int(x0), int(x1) + 1)
    tiles_y = range(int(y0), int(y1) + 1)
    if len(tiles_x) * len(tiles_y) > 36:
        raise ValueError("satellite view area too large")
    mosaic = Image.new("RGB", (256 * len(tiles_x), 256 * len(tiles_y)))
    for i, tx in enumerate(tiles_x):
        for j, ty in enumerate(tiles_y):
            url = (f"https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-{EOX_YEAR}_3857/default/g/"
                   f"{z}/{ty}/{tx}.jpg")
            try:
                mosaic.paste(Image.open(io.BytesIO(_get(url, binary=True))).convert("RGB"),
                             (256 * i, 256 * j))
            except SourceError:
                pass
    crop = mosaic.crop((int((x0 - int(x0)) * 256), int((y0 - int(y0)) * 256),
                        int((x1 - int(x0)) * 256), int((y1 - int(y0)) * 256)))
    buf = io.BytesIO()
    crop.resize((768, 768)).save(buf, "JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode()
