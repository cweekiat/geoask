"""geoask CLI.

  geoask scenes --place tengah --start 2025-01-01 --end 2025-11-30
  geoask change --place tengah --index ndvi --t0 2019-01-01/2019-12-31 --t1 2025-01-01/2025-11-30
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import aoi
from .data.grid import grid_for
from .data.load import load_stack
from .data.stac import find_scenes
from .profiles import load_profile
from .tools import render, spectral
from .tools.scenes import best_date, rank_dates


def _window(s: str) -> tuple[str, str]:
    a, b = s.split("/")
    return a, b


def cmd_scenes(a: argparse.Namespace) -> int:
    prof = load_profile(a.sensor)
    place = aoi.resolve(a.place)
    scenes = find_scenes(prof, place.bbox, a.start, a.end, max_cloud=a.max_cloud)
    print(f"{len(scenes)} scenes from {prof.id} over {place.name} ({aoi.area_km2(place.bbox):.1f} km²)")
    for c in rank_dates(scenes, place.bbox)[: a.top]:
        print(f"  {c.date}  clear in area {c.clear_fraction:6.1%}  tiles {len(c.scenes)}")
    return 0


def cmd_change(a: argparse.Namespace) -> int:
    t_start = time.time()
    prof = load_profile(a.sensor)
    place = aoi.resolve(a.place)
    grid = grid_for(place.bbox, prof.gsd_m)
    targets = spectral.targets_for(a.index) + ["red", "green", "blue"]
    targets = list(dict.fromkeys(targets))
    stacks = []
    for label, win in (("t0", _window(a.t0)), ("t1", _window(a.t1))):
        scenes = find_scenes(prof, place.bbox, *win, max_cloud=a.max_cloud)
        cand = best_date(scenes, place.bbox, min_clear=a.min_clear)
        if cand is None:
            print(f"{label}: no date in {win} with ≥{a.min_clear:.0%} clear pixels in the area")
            return 2
        print(f"{label}: {cand.date} ({cand.clear_fraction:.1%} clear, {len(cand.scenes)} tile(s))")
        stacks.append(load_stack(cand.scenes, targets, grid))
    res = spectral.change(stacks[0], stacks[1], a.index)
    out = Path(a.out) / f"{place.name.replace(' ', '_')}_{a.index}_{res.date0}_{res.date1}"
    out.mkdir(parents=True, exist_ok=True)
    render.true_color_png(stacks[0], out / f"before_{res.date0}.png")
    render.true_color_png(stacks[1], out / f"after_{res.date1}.png")
    render.diverging_png(res.delta, out / f"delta_{a.index}.png")
    render.geotiff(res.delta, stacks[0], out / f"delta_{a.index}.tif")
    summary = res.summary() | {
        "place": place.name,
        "place_bbox_approximate": place.approximate,
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": list(grid.shape)},
        "seconds": round(time.time() - t_start, 1),
    }
    (out / "result.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print(f"outputs → {out}")
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

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
