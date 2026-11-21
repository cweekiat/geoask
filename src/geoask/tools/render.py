"""Write quicklooks (PNG) and analysis layers (GeoTIFF) without extra plotting dependencies."""

from __future__ import annotations

from pathlib import Path

import warnings

import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning

from ..data.load import Stack


def true_color_png(stack: Stack, path: Path, gamma: float = 0.8) -> Path:
    """Needs red/green/blue in the stack. Reflectance 0–0.25 stretched, gamma-brightened."""
    rgb = []
    for t in ("red", "green", "blue"):
        b = stack.bands[t]
        b = np.power(np.clip(np.nan_to_num(b, nan=0) / 0.25, 0, 1), gamma)
        rgb.append((b * 255).astype(np.uint8))
    _write_png(path, np.stack(rgb))
    return path


def diverging_png(delta: np.ndarray, path: Path, vmax: float = 0.5) -> Path:
    """Red = decrease, green = increase, grey = no data."""
    d = np.clip(np.nan_to_num(delta, nan=0) / vmax, -1, 1)
    r = np.where(d < 0, 200 * -d + 55, 55 * (1 - d)).astype(np.uint8)
    g = np.where(d > 0, 200 * d + 55, 55 * (1 + d)).astype(np.uint8)
    b = np.full_like(r, 55)
    nan = np.isnan(delta)
    for c in (r, g, b):
        c[nan] = 128
    _write_png(path, np.stack([r, g, b]))
    return path


def geotiff(arr: np.ndarray, stack: Stack, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=stack.grid.width, height=stack.grid.height, count=1,
        dtype="float32", crs=stack.grid.crs, transform=stack.grid.transform, nodata=np.nan,
        compress="deflate", tiled=True,
    ) as dst:
        dst.write(arr.astype(np.float32), 1)
    return path


def _write_png(path: Path, bands: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c, h, w = bands.shape
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path, "w", driver="PNG", width=w, height=h, count=c, dtype="uint8") as d:
            d.write(bands)

