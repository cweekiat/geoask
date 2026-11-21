"""High-level investigations shared by the CLI, the API server and (later) the apps."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from .. import aoi
from ..data.grid import grid_for
from ..data.load import load_stack
from ..data.stac import find_scenes
from ..profiles import load_profile
from . import render, spectral
from .scenes import best_date

Progress = Callable[[str], None]

INDEX_LABEL = {"ndvi": "vegetation", "mndwi": "open water", "ndwi": "open water",
               "ndbi": "built-up / bare land"}


class NoClearDate(RuntimeError):
    pass


def index_change(
    place: str, index: str, t0: str, t1: str, out_root: Path, sensor: str = "sentinel-2-l2a",
    max_cloud: float = 60, min_clear: float = 0.5, progress: Progress = lambda _m: None,
    bbox: aoi.BBox | None = None,
) -> dict:
    """Change in a spectral index between the clearest dates of two windows ("start/end")."""
    started = time.time()
    prof = load_profile(sensor)
    pl = aoi.place_for(place, bbox)
    where = "the selected area" if pl.source == "drawn" else pl.name.title()
    aoi.check_size(pl, "index_change")
    grid = grid_for(pl.bbox, prof.gsd_m)
    targets = list(dict.fromkeys(spectral.targets_for(index) + ["red", "green", "blue"]))
    stacks, picks = [], []
    for label, win in (("before", t0), ("after", t1)):
        a, b = win.split("/")
        progress(f"Searching {prof.platform} scenes over {where}, {a} to {b}")
        scenes = find_scenes(prof, pl.bbox, a, b, max_cloud=max_cloud)
        progress(f"Ranking {len(scenes)} {label} scenes by clear pixels inside "
                 f"{where}, then re-checking the best for haze")
        cand = best_date(scenes, pl.bbox, min_clear=min_clear)
        if cand is None:
            raise NoClearDate(f"No date between {a} and {b} had at least {min_clear:.0%} of "
                              f"{where} clear of cloud.")
        haze = cand.haze_fraction
        picks.append({"date": cand.date, "clear": round(cand.clear_fraction, 3),
                      "haze": None if haze is None else round(haze, 3),
                      "scenes": [s.id for s in cand.scenes]})
        haze_txt = "" if haze is None else f", {haze:.0%} bright/hazy"
        progress(f"Reading {len(targets)} bands at {prof.gsd_m:g} m for {cand.date} "
                 f"({cand.clear_fraction:.0%} clear{haze_txt})")
        stacks.append(load_stack(cand.scenes, targets, grid))
    progress(f"Computing {index.upper()} change")
    res = spectral.change(stacks[0], stacks[1], index)
    rid = f"{pl.name.replace(' ', '_')}_{index}_{res.date0}_{res.date1}"
    out = Path(out_root) / rid
    out.mkdir(parents=True, exist_ok=True)
    render.true_color_png(stacks[0], out / "before.png")
    render.true_color_png(stacks[1], out / "after.png")
    render.change_png(res.loss, res.gain, out / "delta.png")
    render.geotiff(res.delta, stacks[0], out / "delta.tif")
    result = res.summary() | {
        "id": rid,
        "tool": "index_change",
        "label": INDEX_LABEL.get(index, index),
        "place": pl.name,
        "place_bbox": pl.bbox,
        "place_bbox_approximate": pl.approximate, "place_source": pl.source,
        "corners": grid.corners_lonlat(),
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": list(grid.shape)},
        "picks": picks,
        "images": {"before": "before.png", "after": "after.png", "delta": "delta.png",
                   "geotiff": "delta.tif"},
        "seconds": round(time.time() - started, 1),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2, default=str))
    return result
