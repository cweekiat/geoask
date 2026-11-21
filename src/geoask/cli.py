"""geoask CLI. Places are names anywhere on Earth; --bbox W S E N works everywhere too.

  geoask scenes   --place tengah --start 2025-01-01 --end 2025-11-30
  geoask change   --place tengah --index ndvi --t0 2019-01-01/2019-12-31 --t1 2025-01-01/2025-11-30
  geoask terrain  --place "Mount Faber"
  geoask viewshed --at "48N UG 6387 4975" --radius 3000 --height 10
  geoask activity --bbox 103.74 1.20 103.86 1.26 --window 2026-08-01/2026-11-20
  geoask sharpen  --place "marina bay" --window 2026-01-01/2026-11-20
  geoask mgrs 1.3521 103.8198        # lat lon → MGRS (or an MGRS/UTM string → lat lon)
  geoask fetch sen2sr                # 3.4 MB super-resolution weights (CC0)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import aoi
from .data.stac import find_scenes
from .profiles import load_profile
from .tools import investigate, spectral
from .tools.scenes import rank_dates


def cmd_scenes(a: argparse.Namespace) -> int:
    prof = load_profile(a.sensor)
    place = aoi.resolve(a.place)
    scenes = find_scenes(prof, place.bbox, a.start, a.end, max_cloud=a.max_cloud)
    print(f"{len(scenes)} scenes from {prof.id} over {place.name} ({aoi.area_km2(place.bbox):.1f} km²)")
    for c in rank_dates(scenes, place.bbox)[: a.top]:
        print(f"  {c.date}  clear in area {c.clear_fraction:6.1%}  tiles {len(c.scenes)}")
    return 0


def cmd_change(a: argparse.Namespace) -> int:
    try:
        res = investigate.index_change(
            a.place, a.index, a.t0, a.t1, Path(a.out), sensor=a.sensor,
            max_cloud=a.max_cloud, min_clear=a.min_clear, progress=print,
        )
    except investigate.NoClearDate as e:
        print(e)
        return 2
    print(json.dumps(res, indent=2, default=str))
    print(f"outputs → {Path(a.out) / res['id']}")
    return 0


def _dump(res: dict, out: str) -> int:
    print(json.dumps({k: v for k, v in res.items() if k not in ("corners",)}, indent=2, default=str))
    if "id" in res:
        print(f"outputs → {Path(out) / res['id']}")
    return 0


def _bbox(a: argparse.Namespace):
    return tuple(a.bbox) if a.bbox else None


def cmd_terrain(a: argparse.Namespace) -> int:
    from .tools import terrain

    return _dump(terrain.terrain(a.place, Path(a.out), print, _bbox(a)), a.out)


def cmd_viewshed(a: argparse.Namespace) -> int:
    from . import mgrs
    from .tools import terrain

    pt = mgrs.parse_coordinates(a.at)
    if pt is None:
        print(f"Couldn't read the position {a.at!r} (lat, lon / UTM / MGRS)")
        return 2
    return _dump(terrain.viewshed(*pt, Path(a.out), a.radius, a.height, a.target, print), a.out)


def cmd_activity(a: argparse.Namespace) -> int:
    from .tools import activity

    return _dump(activity.activity(a.place, a.window, Path(a.out), print, _bbox(a), a.passes), a.out)


def cmd_sharpen(a: argparse.Namespace) -> int:
    from .tools import superres

    return _dump(superres.super_resolve(a.place, a.window, Path(a.out), progress=print,
                                        bbox=_bbox(a)), a.out)


def cmd_mgrs(a: argparse.Namespace) -> int:
    from . import mgrs

    text = " ".join(a.value)
    if len(a.value) == 2 and all(v.lstrip("-").replace(".", "", 1).isdigit() for v in a.value):
        lat, lon = map(float, a.value)
        print(mgrs.to_mgrs(lon, lat))
        return 0
    pt = mgrs.parse_coordinates(text)
    if pt is None:
        print(f"Not a coordinate: {text!r}")
        return 2
    print(f"{pt[1]:.6f}, {pt[0]:.6f}")
    return 0


def cmd_fetch(a: argparse.Namespace) -> int:
    if a.model == "sen2sr":
        from .models.superres import fetch_sen2sr

        print(f"SEN2SR-Lite weights (3.4 MB, CC0-1.0) → {fetch_sen2sr()}")
    else:
        print("Clay is large (5.2 GB download, 0.6 GB kept): run python scripts/fetch_clay.py")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    print(f"GeoAsk running at http://{a.host}:{a.port}/app/")
    uvicorn.run(create_app(), host=a.host, port=a.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="geoask")
    ap.add_argument("--sensor", default="sentinel-2-l2a", help="instrument profile id or YAML path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scenes", help="list acquisition dates ranked by clear pixels in the area")
    s.add_argument("--place", required=True)
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.add_argument("--max-cloud", type=float, default=80)
    s.add_argument("--top", type=int, default=10)
    s.set_defaults(fn=cmd_scenes)

    c = sub.add_parser("change", help="spectral-index change between two time windows")
    c.add_argument("--place", required=True)
    c.add_argument("--index", default="ndvi", choices=sorted(spectral.INDICES))
    c.add_argument("--t0", required=True, help="start/end, e.g. 2019-01-01/2019-12-31")
    c.add_argument("--t1", required=True)
    c.add_argument("--max-cloud", type=float, default=60)
    c.add_argument("--min-clear", type=float, default=0.5)
    c.add_argument("--out", default="out")
    c.set_defaults(fn=cmd_change)

    def area(p: argparse.ArgumentParser, window: bool = False) -> argparse.ArgumentParser:
        p.add_argument("--place", help="any place name")
        p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
        if window:
            p.add_argument("--window", required=True, help="start/end, e.g. 2026-01-01/2026-11-20")
        p.add_argument("--out", default="out")
        return p

    area(sub.add_parser("terrain", help="elevation and slope (Copernicus GLO-30)")).set_defaults(fn=cmd_terrain)
    w = sub.add_parser("viewshed", help="what can be seen from a point")
    w.add_argument("--at", required=True, help='"lat, lon", UTM or MGRS')
    w.add_argument("--radius", type=float, default=5000, help="metres (≤ 15000)")
    w.add_argument("--height", type=float, default=2.0, help="observer height above the surface, m")
    w.add_argument("--target", type=float, default=2.0, help="target height, m")
    w.add_argument("--out", default="out")
    w.set_defaults(fn=cmd_viewshed)
    act = area(sub.add_parser("activity", help="vessels per Sentinel-1 pass, unusual days"), True)
    act.add_argument("--passes", type=int, default=24)
    act.set_defaults(fn=cmd_activity)
    area(sub.add_parser("sharpen", help="2.5 m super-resolved view (display only)"), True).set_defaults(fn=cmd_sharpen)
    m = sub.add_parser("mgrs", help="convert between lat/lon, UTM and MGRS")
    m.add_argument("value", nargs="+")
    m.set_defaults(fn=cmd_mgrs)
    f = sub.add_parser("fetch", help="download optional model weights")
    f.add_argument("model", choices=["sen2sr", "clay"])
    f.set_defaults(fn=cmd_fetch)

    v = sub.add_parser("serve", help="run the local investigation app")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8787)
    v.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
