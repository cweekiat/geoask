"""Change detection with any registered foundation model's patch embeddings.

For each date the model embeds every chip; patch tokens (Clay: 8×8 px = 80 m at 10 m) are compared
by cosine distance between dates and mosaicked back onto the grid (overlapping chips averaged).
Unlike a spectral index this captures *any* change the model represents — new buildings, cleared
land, new water — without choosing an index first.

The model id is a parameter: Clay today, any other ``geoask.models`` adapter tomorrow.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .. import aoi
from ..data.grid import grid_for
from ..data.load import load_stack
from ..data.stac import find_scenes
from ..models import Embeddings, get
from ..profiles import load_profile
from . import render
from .investigate import NoClearDate, Progress
from .scenes import best_date


def patch_distance_map(e0: Embeddings, e1: Embeddings) -> tuple[np.ndarray, int]:
    """Cosine distance per patch, mosaicked to the grid at patch resolution (NaN = no data)."""
    if e0.patches is None or e1.patches is None:
        raise ValueError(f"{e0.model_id} gives no patch tokens")
    if (e0.model_id, e0.model_version) != (e1.model_id, e1.model_version):
        raise ValueError("can't compare embeddings from different models")
    if e0.chip_origins != e1.chip_origins:
        raise ValueError("the two dates were chipped differently")
    _, ph, pw, _ = e0.patches.shape
    step = e0.chip_size // ph  # pixels per patch
    H, W = e0.grid_shape
    acc = np.zeros((-(-max(H, e0.chip_size) // step), -(-max(W, e0.chip_size) // step)))
    cnt = np.zeros_like(acc)
    for i, (r, c) in enumerate(e0.chip_origins):
        a = e0.patches[i].astype(np.float32)
        b = e1.patches[i].astype(np.float32)
        cos = (a * b).sum(-1) / (np.linalg.norm(a, axis=-1) * np.linalg.norm(b, axis=-1) + 1e-8)
        r0, c0 = r // step, c // step
        acc[r0:r0 + ph, c0:c0 + pw] += 1 - cos
        cnt[r0:r0 + ph, c0:c0 + pw] += 1
    with np.errstate(invalid="ignore"):
        d = acc / cnt
    return d[: -(-H // step), : -(-W // step)], step


def upsample(patch_map: np.ndarray, step: int, shape: tuple[int, int]) -> np.ndarray:
    return np.kron(patch_map, np.ones((step, step)))[: shape[0], : shape[1]]


def otsu_threshold(d: np.ndarray, bins: int = 256) -> float:
    """Otsu's threshold: the cut that best separates 'changed' from 'unchanged' patch distances.

    The standard unsupervised choice for change detection; it adapts to how much of the area
    changed, where a median + k·MAD rule gets too strict when change is widespread.
    """
    v = d[np.isfinite(d)]
    hist, edges = np.histogram(v, bins)
    centres = (edges[:-1] + edges[1:]) / 2
    w = np.cumsum(hist).astype(float)
    m = np.cumsum(hist * centres)
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (m[-1] * w / w[-1] - m) ** 2 / (w * (w[-1] - w))
    return float(centres[np.nanargmax(between)])


def embedding_change(
    place: str, t0: str, t1: str, out_root: Path, model: str = "clay-v1.5",
    sensor: str = "sentinel-2-l2a", max_cloud: float = 60, min_clear: float = 0.5,
    progress: Progress = lambda _m: None, bbox: aoi.BBox | None = None,
) -> dict:
    started = time.time()
    prof = load_profile(sensor)
    pl = aoi.place_for(place, bbox)
    where = "the selected area" if pl.source == "drawn" else aoi.label(pl)
    aoi.check_size(pl, "embedding_change")
    grid = grid_for(pl.bbox, prof.gsd_m)
    enc = get(model)
    progress(f"Loading {enc.spec.family} on this device")
    enc.load()
    keys = enc.select_bands(prof)
    vis = [k for k in ("red", "green", "blue") if k not in keys]
    embs, stacks, picks = [], [], []
    for label, win in (("before", t0), ("after", t1)):
        a, b = win.split("/")
        progress(f"Finding the clearest {label} date over {where}, {a} to {b}")
        cand = best_date(find_scenes(prof, pl.bbox, a, b, max_cloud=max_cloud), pl.bbox,
                         min_clear=min_clear)
        if cand is None:
            raise NoClearDate(f"No date between {a} and {b} had at least {min_clear:.0%} of "
                              f"{where} clear of cloud.")
        progress(f"Reading {len(keys)} bands for {cand.date}")
        st = load_stack(cand.scenes, keys + vis, grid)
        progress(f"Embedding {cand.date} with {enc.spec.id}")
        embs.append(enc.embed_stack(st, cand.scenes[0].profile))
        stacks.append(st)
        picks.append({"date": cand.date, "clear": round(cand.clear_fraction, 3),
                      "haze": None if cand.haze_fraction is None else round(cand.haze_fraction, 3),
                      "scenes": [s.id for s in cand.scenes]})
    progress("Comparing embeddings patch by patch")
    pmap, step = patch_distance_map(*embs)
    dist = upsample(pmap, step, grid.shape).astype(np.float32)
    both = stacks[0].valid & stacks[1].valid
    dist[~both] = np.nan
    thr = otsu_threshold(dist)
    changed = np.isfinite(dist) & (dist > thr)
    px_ha = grid.pixel_area_m2 / 10_000

    rid = f"{pl.name.replace(' ', '_')}_{enc.spec.id}_{picks[0]['date']}_{picks[1]['date']}"
    out = Path(out_root) / rid
    out.mkdir(parents=True, exist_ok=True)
    render.true_color_png(stacks[0], out / "before.png")
    render.true_color_png(stacks[1], out / "after.png")
    render.heat_png(dist, changed, out / "delta.png")
    render.geotiff(dist, stacks[0], out / "delta.tif")
    result = {
        "id": rid, "tool": "embedding_change", "model": f"{enc.spec.id}@{enc.version}",
        "label": "any change", "index": enc.spec.family.lower(),
        "place": pl.name, "place_bbox": pl.bbox, "place_bbox_approximate": pl.approximate, "place_source": pl.source,
        "date0": picks[0]["date"], "date1": picks[1]["date"], "sensor": prof.id,
        "changed_ha": round(float(changed.sum() * px_ha), 2),
        "threshold": round(thr, 4), "threshold_method": "Otsu on patch cosine distances",
        "median_distance": round(float(np.nanmedian(dist)), 4),
        "patch_m": step * grid.res, "compared_fraction": round(float(both.mean()), 3),
        "area_ha": round(float(both.size * px_ha), 2),
        "corners": grid.corners_lonlat(),
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": list(grid.shape)},
        "picks": picks,
        "images": {"before": "before.png", "after": "after.png", "delta": "delta.png",
                   "geotiff": "delta.tif"},
        "seconds": round(time.time() - started, 1),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2, default=str))
    np.save(out / "distance_patch.npy", pmap.astype(np.float32))
    return result
