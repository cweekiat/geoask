"""Terrain from the Copernicus GLO-30 DEM: elevation and slope, a point's elevation, line of sight
and viewshed. Global, free and keyless.

GLO-30 is a 30 m *surface* model (radar, 2011–2015): it includes buildings and tree canopy, so in
cities it measures roof-level heights, coarsely. Tiles are 1° COGs on AWS with predictable names;
tiles that would be all sea don't exist, and their pixels read as 0 m.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError

from .. import aoi
from ..data.cog import read_to_grid
from ..data.grid import Grid, grid_for
from . import render

Progress = Callable[[str], None]
SOURCE = "Copernicus GLO-30 DEM"
RES_M = 30.0
_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_"
        "{ew}{lon:03d}_00_DEM/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")
EARTH_R = 6_371_000.0
REFRACTION = 0.13  # standard atmospheric refraction coefficient


def tile_urls(bbox: aoi.BBox) -> list[str]:
    w, s, e, n = bbox
    out = []
    for lat in range(math.floor(s), math.floor(n - 1e-9) + 1):
        for lon in range(math.floor(w), math.floor(e - 1e-9) + 1):
            out.append(_URL.format(ns="N" if lat >= 0 else "S", lat=abs(lat),
                                   ew="E" if lon >= 0 else "W", lon=abs(lon)))
    return out


def dem_on(grid: Grid, bbox: aoi.BBox) -> np.ndarray:
    """DEM warped onto ``grid`` (metres). Missing (all-sea) tiles count as 0 m."""
    def read(url: str) -> np.ndarray | None:
        try:
            # GLO-30 tiles declare no nodata, so pixels outside a tile would read as 0 m:
            # an explicit fill value marks them as missing instead.
            return read_to_grid(url, grid, Resampling.bilinear, nodata=-32767.0)
        except RasterioIOError:
            return None

    with ThreadPoolExecutor(4) as ex:
        parts = [p for p in ex.map(read, tile_urls(bbox)) if p is not None]
    dem = np.full(grid.shape, np.nan, np.float32)
    for p in parts:
        dem = np.where(np.isnan(dem), p, dem)
    return np.nan_to_num(dem, nan=0.0)


def elevation_at(lon: float, lat: float) -> float | None:
    url = tile_urls((lon, lat, lon + 1e-6, lat + 1e-6))[0]
    try:
        from ..data.cog import GDAL_ENV

        with rasterio.Env(**GDAL_ENV), rasterio.open(url) as src:
            v = next(src.sample([(lon, lat)]))[0]
        return float(v)
    except RasterioIOError:
        return 0.0  # no tile: open sea
    except (StopIteration, IndexError, ValueError):
        return None


def slope_deg(dem: np.ndarray, res: float) -> np.ndarray:
    gy, gx = np.gradient(dem, res)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def hillshade(dem: np.ndarray, res: float, az: float = 315, alt: float = 45) -> np.ndarray:
    gy, gx = np.gradient(dem, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(az), math.radians(alt)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


# ---- relief: elevation and slope over an area ---------------------------------------------

_RAMP = np.array([  # elevation fraction → colour (navy lowlands → teal → sand → white peaks)
    [0.00, 22, 54, 92], [0.25, 40, 120, 140], [0.50, 120, 170, 120],
    [0.75, 200, 180, 130], [1.00, 245, 245, 245]], np.float32)


def relief_png(dem: np.ndarray, res: float, path: Path) -> Path:
    lo, hi = np.percentile(dem, 1), np.percentile(dem, 99)
    t = np.clip((dem - lo) / max(hi - lo, 1.0), 0, 1)
    rgb = np.stack([np.interp(t, _RAMP[:, 0], _RAMP[:, i]) for i in (1, 2, 3)])
    shade = 0.55 + 0.45 * hillshade(dem, res)
    rgba = np.concatenate([(rgb * shade).astype(np.uint8), np.full((1, *dem.shape), 215, np.uint8)])
    render._write_png(path, rgba)
    return path


def terrain(place: str | None, out_root: Path, progress: Progress = lambda _m: None,
            bbox: aoi.BBox | None = None) -> dict:
    started = time.time()
    pl = aoi.place_for(place, bbox)
    aoi.check_size(pl, "terrain")
    where = "the selected area" if pl.source == "drawn" else aoi.label(pl)
    grid = grid_for(pl.bbox, RES_M)
    progress(f"Reading the {SOURCE} over {where} ({len(tile_urls(pl.bbox))} tile(s))")
    dem = dem_on(grid, pl.bbox)
    progress("Computing slope and relief")
    slope = slope_deg(dem, grid.res)
    rid = f"{_slug(pl.name)}_terrain_" + "_".join(f"{v:.4f}" for v in pl.bbox)
    out = Path(out_root) / rid
    out.mkdir(parents=True, exist_ok=True)
    relief_png(dem, grid.res, out / "overlay.png")
    px_ha = grid.pixel_area_m2 / 1e4
    hi = np.unravel_index(int(np.argmax(dem)), dem.shape)
    hx, hy = grid.transform @ (hi[1] + 0.5, hi[0] + 0.5)
    from rasterio.warp import transform as wt

    hlon, hlat = wt(grid.crs, "EPSG:4326", [hx], [hy])
    result = {
        "id": rid, "tool": "terrain", "source": SOURCE,
        "place": pl.name, "place_bbox": pl.bbox, "place_bbox_approximate": pl.approximate,
        "place_source": pl.source, "corners": grid.corners_lonlat(),
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": list(grid.shape)},
        "elev_min_m": float(np.min(dem)), "elev_max_m": float(np.max(dem)),
        "elev_mean_m": float(np.mean(dem)), "relief_m": float(np.max(dem) - np.min(dem)),
        "highest_point": [round(hlon[0], 6), round(hlat[0], 6)],
        "slope_mean_deg": float(np.mean(slope)),
        "steep_ha": float((slope > 15).sum() * px_ha), "very_steep_ha": float((slope > 30).sum() * px_ha),
        "area_ha": float(dem.size * px_ha),
        "images": {"overlay": "overlay.png"},
        "seconds": round(time.time() - started, 1),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2))
    return result


# ---- visibility -----------------------------------------------------------------------------

def _curvature_drop(d: np.ndarray) -> np.ndarray:
    return d * d / (2 * EARTH_R) * (1 - REFRACTION)


def viewshed_array(dem: np.ndarray, r0: int, c0: int, res: float, observer_h: float,
                   target_h: float, radius_px: int) -> np.ndarray:
    """Cells visible from (r0, c0): rays to every cell on the radius square's edge; a cell is
    visible if its sight angle is at least the highest angle passed so far on its ray."""
    h, w = dem.shape
    vis = np.zeros_like(dem, dtype=bool)
    vis[r0, c0] = True
    z0 = dem[r0, c0] + observer_h
    edge = [(r0 - radius_px, c) for c in range(c0 - radius_px, c0 + radius_px + 1)]
    edge += [(r0 + radius_px, c) for c in range(c0 - radius_px, c0 + radius_px + 1)]
    edge += [(r, c0 - radius_px) for r in range(r0 - radius_px + 1, r0 + radius_px)]
    edge += [(r, c0 + radius_px) for r in range(r0 - radius_px + 1, r0 + radius_px)]
    for re_, ce in edge:
        n = max(abs(re_ - r0), abs(ce - c0))
        t = np.arange(1, n + 1) / n
        rr = np.rint(r0 + t * (re_ - r0)).astype(int)
        cc = np.rint(c0 + t * (ce - c0)).astype(int)
        ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
        rr, cc = rr[ok], cc[ok]
        if not rr.size:
            continue
        d = np.hypot(rr - r0, cc - c0) * res
        inside = d <= radius_px * res
        rr, cc, d = rr[inside], cc[inside], d[inside]
        drop = _curvature_drop(d)
        ang_ground = (dem[rr, cc] - drop - z0) / d
        ang_target = (dem[rr, cc] + target_h - drop - z0) / d
        prior = np.maximum.accumulate(np.concatenate([[-np.inf], ang_ground[:-1]]))
        vis[rr, cc] |= ang_target >= prior
    return vis


def viewshed(lon: float, lat: float, out_root: Path, radius_m: float = 5000,
             observer_h: float = 2.0, target_h: float = 2.0,
             progress: Progress = lambda _m: None) -> dict:
    started = time.time()
    radius_m = float(min(max(radius_m, 200), 15000))
    dlat = radius_m / 110_570
    dlon = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    bbox = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)
    grid = grid_for(bbox, RES_M)
    progress(f"Reading the {SOURCE} within {radius_m / 1000:g} km")
    dem = dem_on(grid, bbox)
    from rasterio.warp import transform as wt

    xs, ys = wt("EPSG:4326", grid.crs, [lon], [lat])
    c0, r0 = (~grid.transform) @ (xs[0], ys[0])
    r0, c0 = int(r0), int(c0)
    progress(f"Tracing sight lines from a {observer_h:g} m observer to {target_h:g} m targets")
    vis = viewshed_array(dem, r0, c0, grid.res, observer_h, target_h, int(radius_m / grid.res))
    yy, xx = np.mgrid[0:dem.shape[0], 0:dem.shape[1]]
    disk = np.hypot(yy - r0, xx - c0) * grid.res <= radius_m
    vis &= disk
    rid = f"viewshed_{lat:.5f}_{lon:.5f}_{int(radius_m)}_{observer_h:g}_{target_h:g}"
    out = Path(out_root) / rid
    out.mkdir(parents=True, exist_ok=True)
    rgba = np.zeros((4, *dem.shape), np.uint8)
    rgba[0], rgba[1], rgba[2] = 52, 209, 196  # teal = visible
    rgba[3] = np.where(vis, 150, np.where(disk, 0, 0)).astype(np.uint8)
    hidden = disk & ~vis
    rgba[0][hidden], rgba[1][hidden], rgba[2][hidden], rgba[3][hidden] = 7, 11, 18, 120  # dim = hidden
    render._write_png(out / "overlay.png", rgba)
    px_ha = grid.pixel_area_m2 / 1e4
    result = {
        "id": rid, "tool": "viewshed", "source": SOURCE,
        "place": "viewshed", "place_source": "point", "observer": [lon, lat],
        "place_bbox": bbox, "place_bbox_approximate": False,
        "corners": grid.corners_lonlat(),
        "grid": {"crs": grid.crs, "res_m": grid.res, "shape": list(grid.shape)},
        "radius_m": radius_m, "observer_h_m": observer_h, "target_h_m": target_h,
        "observer_elev_m": float(dem[r0, c0]),
        "visible_ha": float(vis.sum() * px_ha), "area_ha": float(disk.sum() * px_ha),
        "images": {"overlay": "overlay.png"},
        "seconds": round(time.time() - started, 1),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2))
    return result


def line_of_sight(a: tuple[float, float], b: tuple[float, float], observer_h: float = 2.0,
                  target_h: float = 2.0) -> dict:
    """Is b visible from a? Returns the first blocking point, if any, and the terrain profile."""
    w, e = min(a[0], b[0]), max(a[0], b[0])
    s, n = min(a[1], b[1]), max(a[1], b[1])
    pad = 0.002
    bbox = (w - pad, s - pad, e + pad, n + pad)
    if aoi.area_km2(bbox) > 2500:
        raise ValueError("Line of sight is limited to about 50 km.")
    grid = grid_for(bbox, RES_M)
    dem = dem_on(grid, bbox)
    from rasterio.warp import transform as wt

    xs, ys = wt("EPSG:4326", grid.crs, [a[0], b[0]], [a[1], b[1]])
    inv = ~grid.transform
    (ca, ra), (cb, rb) = inv @ (xs[0], ys[0]), inv @ (xs[1], ys[1])
    dist = math.hypot(xs[1] - xs[0], ys[1] - ys[0])
    k = max(int(dist / (grid.res / 2)), 2)
    t = np.linspace(0, 1, k + 1)
    rr = np.clip(np.rint(ra + t * (rb - ra)).astype(int), 0, dem.shape[0] - 1)
    cc = np.clip(np.rint(ca + t * (cb - ca)).astype(int), 0, dem.shape[1] - 1)
    ground = dem[rr, cc]
    d = t * dist
    drop = _curvature_drop(d)
    z0, z1 = ground[0] + observer_h, ground[-1] + target_h
    sight = z0 + (z1 - z0) * t
    clearance = sight - (ground - drop)
    blocked = np.where(clearance[1:-1] < 0)[0]
    first = None
    if blocked.size:
        i = int(blocked[0]) + 1
        bx, by = grid.transform @ (cc[i] + 0.5, rr[i] + 0.5)
        lo, la = wt(grid.crs, "EPSG:4326", [bx], [by])
        first = {"lonlat": [round(lo[0], 6), round(la[0], 6)], "distance_m": float(d[i]),
                 "above_sightline_m": float(-clearance[i])}
    return {"tool": "line_of_sight", "source": SOURCE, "visible": first is None,
            "distance_m": float(dist), "from": list(a), "to": list(b),
            "observer_h_m": observer_h, "target_h_m": target_h,
            "min_clearance_m": float(clearance[1:-1].min()) if k > 2 else float(clearance.min()),
            "first_obstruction": first,
            "profile": [[round(float(x), 1), round(float(z), 1)] for x, z in
                        zip(d[:: max(1, k // 200)], ground[:: max(1, k // 200)])]}


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in s.lower())[:40] or "area"
