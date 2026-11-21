"""Sharpen the clearest recent Sentinel-2 image of an area from 10 m to 2.5 m, for viewing.

Display only: nothing GeoAsk measures uses the super-resolved pixels. The result carries a
consistency map (super-resolved image averaged back to 10 m vs the real 10 m image) so the viewer
can see where the added detail is least trustworthy.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .. import aoi
from ..data.grid import grid_for
from ..data.load import load_stack
from ..data.stac import find_scenes
from ..models.superres import consistency, get_super_resolver
from ..profiles import load_profile
from . import render
from .investigate import NoClearDate
from .scenes import best_date

Progress = Callable[[str], None]


def _rgb_png(r, g, b, valid, path: Path, gamma: float = 0.8) -> None:
    chans = [(np.power(np.clip(np.nan_to_num(c, nan=0) / 0.25, 0, 1), gamma) * 255).astype(np.uint8)
             for c in (r, g, b)]
    render._write_png(path, np.stack([*chans, np.where(valid, 255, 0).astype(np.uint8)]))


def super_resolve(place: str | None, window: str, out_root: Path, model: str = "sen2sr-lite",
                  progress: Progress = lambda _m: None, bbox: aoi.BBox | None = None,
                  min_clear: float = 0.7) -> dict:
    started = time.time()
    pl = aoi.place_for(place, bbox)
    aoi.check_size(pl, "super_resolve")
    where = "the selected area" if pl.source == "drawn" else aoi.label(pl)
    progress(f"Loading {model}")
    sr = get_super_resolver(model)
    prof = load_profile("sentinel-2-l2a")
    grid = grid_for(pl.bbox, prof.gsd_m)
    a, b = window.split("/")
    progress(f"Finding the clearest image of {where}, {a} to {b}")
    cand = best_date(find_scenes(prof, pl.bbox, a, b, max_cloud=40), pl.bbox, min_clear=min_clear)
    if cand is None:
        raise NoClearDate(f"No date between {a} and {b} had {min_clear:.0%} of {where} clear.")
    progress(f"Reading red, green, blue and near-infrared at 10 m for {cand.date}")
    st = load_stack(cand.scenes, list(sr.spec.bands), grid)
    lr = np.stack([st.bands[t] for t in sr.spec.bands]).astype(np.float32)
    progress(f"Super-resolving {grid.width} × {grid.height} px to "
             f"{grid.width * sr.spec.scale} × {grid.height * sr.spec.scale} px (2.5 m)")
    hr = sr.predict(lr)
    cons = consistency(np.nan_to_num(lr, nan=0), hr, sr.spec.scale)
    rid = f"{''.join(c if c.isalnum() else '_' for c in pl.name.lower())[:40]}_sr_{cand.date}"
    out = Path(out_root) / rid
    out.mkdir(parents=True, exist_ok=True)
    _rgb_png(lr[0], lr[1], lr[2], st.valid, out / "before.png")
    up_valid = np.repeat(np.repeat(st.valid, sr.spec.scale, 0), sr.spec.scale, 1)
    _rgb_png(hr[0], hr[1], hr[2], up_valid, out / "after.png")
    # consistency overlay: amber where averaging the 2.5 m image back to 10 m departs from the real
    # pixel by more than 0.01 reflectance (≈ 1 % albedo)
    t = np.clip((cons - 0.005) / 0.02, 0, 1)
    rgba = np.zeros((4, *cons.shape), np.uint8)
    rgba[0], rgba[1], rgba[2] = 255, 196, 92
    rgba[3] = np.where(st.valid, (t * 200).astype(np.uint8), 0)
    render._write_png(out / "delta.png", rgba)
    v = st.valid
    result = {
        "id": rid, "tool": "super_resolve", "model": f"{sr.spec.id}", "licence": sr.spec.licence,
        "citation": sr.spec.citation, "display_only": True,
        "place": pl.name, "place_bbox": pl.bbox, "place_bbox_approximate": pl.approximate,
        "place_source": pl.source, "corners": grid.corners_lonlat(),
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": list(grid.shape)},
        "out_res_m": grid.res / sr.spec.scale,
        "date": cand.date, "date0": cand.date, "date1": cand.date,
        "clear_fraction": round(cand.clear_fraction, 3),
        "scenes": [s.id for s in cand.scenes],
        "consistency_mean": float(np.nanmean(cons[v])) if v.any() else None,
        "consistency_p95": float(np.nanpercentile(cons[v], 95)) if v.any() else None,
        "images": {"before": "before.png", "after": "after.png", "delta": "delta.png"},
        "seconds": round(time.time() - started, 1),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2))
    return result
