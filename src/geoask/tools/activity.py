"""Pattern of life: how busy is an area, pass by pass, and which days were unusual?

Sentinel-1 radar sees through cloud, day and night, so every pass counts (about every 6–12 days
per orbit direction). On each pass the vessel detector runs with SAHI-style slicing; the counts
form a time series, and days far from the usual level (median ± 3 robust standard deviations)
are flagged. Positions are kept, so the map shows *where* activity concentrates.

Measured: how many radar-bright targets on open water, per pass. Not measured: what or whose
they are (no AIS), or anything under about 20–30 m long.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .. import aoi, mgrs
from ..data.grid import grid_for
from ..data.load import load_stack
from ..data.stac import find_scenes, group_by_date
from ..detect.sar_vessels import SarVesselCFAR
from ..detect.slicing import sliced_detect
from ..profiles import load_profile
from . import render

Progress = Callable[[str], None]
MAX_PASSES = 24


def robust_anomalies(counts: list[int], z: float = 3.0) -> tuple[float, float, list[int]]:
    """(median, robust sd, indices of unusual passes). Robust sd = 1.4826 × MAD, floored at 1 so a
    perfectly steady series doesn't flag a difference of one vessel."""
    a = np.asarray(counts, float)
    med = float(np.median(a)) if a.size else 0.0
    sd = max(1.4826 * float(np.median(np.abs(a - med))) if a.size else 0.0, 1.0)
    return med, sd, [i for i, c in enumerate(a) if abs(c - med) > z * sd]


def _xy(crs: str, lon: float, lat: float) -> tuple[float, float]:
    from rasterio.warp import transform as wt

    xs, ys = wt("EPSG:4326", crs, [lon], [lat])
    return xs[0], ys[0]


def _near_any(p: dict, spots: list[tuple[float, float]], m: float = 30.0) -> bool:
    k = np.cos(np.radians(p["lat"])) * 111_320
    return any(np.hypot((p["lon"] - lo) * k, (p["lat"] - la) * 110_570) <= m for lo, la in spots)


def fixed_targets(points: list[dict], passes: int, share: float = 0.8,
                  m: float = 30.0) -> list[tuple[float, float]]:
    """Spots (lon, lat) where a detection appears on at least ``share`` of the passes."""
    if passes < 3 or not points:
        return []
    k = np.cos(np.radians(points[0]["lat"])) * 111_320
    cells: dict[tuple[int, int], set[str]] = {}
    where: dict[tuple[int, int], tuple[float, float]] = {}
    for p in points:  # bin to 30 m cells; a cell and its neighbours count together
        key = (int(p["lon"] * k // m), int(p["lat"] * 110_570 // m))
        cells.setdefault(key, set()).add(p["date"])
        where.setdefault(key, (p["lon"], p["lat"]))
    out = []
    for cx, cy in cells:
        dates = set().union(*(cells.get((cx + dx, cy + dy), set())
                              for dx in (-1, 0, 1) for dy in (-1, 0, 1)))
        if len(dates) >= share * passes:
            out.append(where[(cx, cy)])
    return out


def activity(place: str | None, window: str, out_root: Path, progress: Progress = lambda _m: None,
             bbox: aoi.BBox | None = None, max_passes: int = MAX_PASSES) -> dict:
    started = time.time()
    pl = aoi.place_for(place, bbox)
    aoi.check_size(pl, "activity")
    where = "the selected area" if pl.source == "drawn" else aoi.label(pl)
    prof = load_profile("sentinel-1-rtc")
    grid = grid_for(pl.bbox, prof.gsd_m)
    a, b = window.split("/")
    progress(f"Searching Sentinel-1 radar passes over {where}, {a} to {b}")
    by_date = group_by_date(find_scenes(prof, pl.bbox, a, b, max_cloud=None, limit=300))
    dates = sorted(by_date)
    if len(dates) > max_passes:  # spread evenly over the window
        dates = [dates[round(i)] for i in np.linspace(0, len(dates) - 1, max_passes)]
    if not dates:
        raise RuntimeError(f"No Sentinel-1 passes over {where} between {a} and {b}.")
    det = SarVesselCFAR()
    series, points = [], []
    density = np.zeros(grid.shape, np.float32)
    inv = None
    from rasterio.warp import transform as wt

    # Reading the radar dominates the time, so up to 3 passes download while one is analysed.
    pool = ThreadPoolExecutor(3)
    stacks = pool.map(lambda d: load_stack(by_date[d], ["vv"], grid), dates)
    for k, (d, st) in enumerate(zip(dates, stacks), 1):
        progress(f"Pass {k} of {len(dates)}: {d}, detecting vessels in 512 px slices")
        coverage = float(np.isfinite(st.bands["vv"]).mean())
        if coverage < 0.6:
            continue  # the pass only clipped the area: counts wouldn't be comparable
        boxes = sliced_detect({"vv": st.bands["vv"]}, det, size=512, overlap=0.2)
        xs, ys = [], []
        for bx in boxes:
            cx, cy = (bx.x0 + bx.x1) / 2, (bx.y0 + bx.y1) / 2
            density[min(int(cy), grid.height - 1), min(int(cx), grid.width - 1)] += 1
            x, y = grid.transform @ (cx, cy)
            xs.append(x)
            ys.append(y)
        if xs:
            lons, lats = wt(grid.crs, "EPSG:4326", xs, ys)
            for bx, lo, la in zip(boxes, lons, lats):
                length = max(bx.x1 - bx.x0, bx.y1 - bx.y0) * grid.res
                points.append({"date": d, "lon": round(lo, 6), "lat": round(la, 6),
                               "mgrs": mgrs.to_mgrs(lo, la, 4), "length_m": round(length),
                               "score": round(bx.score, 2)})
        props = by_date[d][0].item.properties
        orbit = f"{props.get('sat:orbit_state', '?')} {props.get('sat:relative_orbit', '?')}"
        series.append({"date": d, "count": len(boxes), "coverage": round(coverage, 2),
                       "orbit": orbit, "scenes": [s.id for s in by_date[d]]})
    del inv
    pool.shutdown(wait=False)
    if not series:
        raise RuntimeError(f"No Sentinel-1 pass covered most of {where}.")
    # Persistent targets show up in the same spot on almost every pass: beacons, platforms,
    # islets, or vessels laid up for months. They aren't traffic, so counts leave out anything
    # within 30 m of a spot seen on ≥ 90 % of passes (reported separately).
    fixed = fixed_targets(points, len(series), share=0.9)
    if fixed:
        progress(f"Setting aside {len(fixed)} persistent target(s) seen in the same spot on "
                 "almost every pass")
        keep = [p for p in points if not _near_any(p, fixed)]
        for srow in series:
            srow["count"] = sum(1 for p in keep if p["date"] == srow["date"])
        density[:] = 0
        for p in keep:
            c, r = (~grid.transform) @ _xy(grid.crs, p["lon"], p["lat"])
            density[min(max(int(r), 0), grid.height - 1), min(max(int(c), 0), grid.width - 1)] += 1
        points = keep
    counts = [s["count"] for s in series]
    med, sd, _ = robust_anomalies(counts)
    # Each orbit sees the sea from its own side and angle, and at its own time of day, so a pass
    # is only compared with passes from the same relative orbit (needs at least 4 of them).
    idx: list[int] = []
    for orbit in sorted({s["orbit"] for s in series}):
        members = [i for i, s in enumerate(series) if s["orbit"] == orbit]
        if len(members) >= 4:
            omed, _, oidx = robust_anomalies([counts[i] for i in members])
            for j in oidx:
                series[members[j]]["baseline"] = omed
            idx += [members[j] for j in oidx]
    idx.sort()
    for i in idx:
        series[i]["unusual"] = "busier" if counts[i] > series[i]["baseline"] else "quieter"
    rid = (f"{''.join(c if c.isalnum() else '_' for c in pl.name.lower())[:40]}_activity_"
           f"{series[0]['date']}_{series[-1]['date']}")
    out = Path(out_root) / rid
    out.mkdir(parents=True, exist_ok=True)
    from scipy import ndimage

    heat = ndimage.gaussian_filter(density, sigma=6)
    t = np.clip(heat / max(float(heat.max()), 1e-9), 0, 1)
    rgba = np.zeros((4, *heat.shape), np.uint8)
    rgba[0] = (255 * np.clip(0.4 + t, 0, 1)).astype(np.uint8)
    rgba[1] = (196 * t + 60).astype(np.uint8)
    rgba[2] = (92 * (1 - t)).astype(np.uint8)
    rgba[3] = np.where(t > 0.04, (60 + 180 * t), 0).astype(np.uint8)
    render._write_png(out / "overlay.png", rgba)
    (out / "detections.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {k: v for k, v in p.items() if k not in ("lon", "lat")},
         "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]}} for p in points]}))
    result = {
        "id": rid, "tool": "activity", "detector": det.id, "sensor": "Sentinel-1 RTC (VV)",
        "slicing": {"size_px": 512, "overlap": 0.2, "merge": "greedy NMM, IoS 0.5"},
        "place": pl.name, "place_bbox": pl.bbox, "place_bbox_approximate": pl.approximate,
        "place_source": pl.source, "corners": grid.corners_lonlat(),
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": list(grid.shape)},
        "date0": series[0]["date"], "date1": series[-1]["date"],
        "passes": len(series), "series": series,
        "mean_count": float(np.mean(counts)), "median_count": med, "max_count": max(counts),
        "max_date": series[int(np.argmax(counts))]["date"], "robust_sd": sd,
        "unusual": [{"date": series[i]["date"], "count": counts[i], "kind": series[i]["unusual"],
                     "orbit": series[i]["orbit"], "orbit_median": series[i]["baseline"]}
                    for i in idx],
        "orbits": sorted({s["orbit"] for s in series}),
        "detections": len(points), "persistent_targets": len(fixed),
        "persistent": [{"lon": round(lo, 6), "lat": round(la, 6), "mgrs": mgrs.to_mgrs(lo, la, 4)}
                       for lo, la in fixed],
        "images": {"overlay": "overlay.png", "points": "detections.geojson"},
        "seconds": round(time.time() - started, 1),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2))
    return result
