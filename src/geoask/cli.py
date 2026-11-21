"""geoask CLI.

  geoask scenes --place tengah --start 2025-01-01 --end 2025-11-30
  geoask change --place tengah --index ndvi --t0 2019-01-01/2019-12-31 --t1 2025-01-01/2025-11-30
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

    v = sub.add_parser("serve", help="run the local investigation app")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8787)
    v.set_defaults(fn=cmd_serve)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
