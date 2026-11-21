"""Write quicklooks (PNG) and analysis layers (GeoTIFF) without extra plotting dependencies."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning

from ..data.load import Stack


def true_color_png(stack: Stack, path: Path, gamma: float = 0.8) -> Path:
    """RGBA quicklook. Reflectance 0–0.25 stretched, gamma-brightened; masked pixels transparent."""
    rgb = []
    for t in ("red", "green", "blue"):
        b = stack.bands[t]
        b = np.power(np.clip(np.nan_to_num(b, nan=0) / 0.25, 0, 1), gamma)
        rgb.append((b * 255).astype(np.uint8))
    alpha = np.where(stack.valid, 255, 0).astype(np.uint8)  # cloud gaps are transparent
    _write_png(path, np.stack([*rgb, alpha]))
    return path


LOSS_RGB = (255, 122, 69)  # warm orange: crossed from high to low index
GAIN_RGB = (52, 209, 196)  # teal: crossed from low to high index


def change_png(loss: np.ndarray, gain: np.ndarray, path: Path) -> Path:
    """RGBA overlay of exactly the pixels counted in loss/gain hectares, so map and numbers agree.

    Orange/teal is easier to tell apart than red/green; the UI also labels both in text.
    """
    rgba = np.zeros((4, *loss.shape), np.uint8)
    for mask, rgb in ((loss, LOSS_RGB), (gain, GAIN_RGB)):
        for i, c in enumerate(rgb):
            rgba[i][mask] = c
        rgba[3][mask] = 230
    _write_png(path, rgba)
    return path


def heat_png(dist: np.ndarray, changed: np.ndarray, path: Path) -> Path:
    """Embedding-change overlay: patches above the threshold in a blue→white ramp by strength.

    Only the pixels counted as changed are painted, so the map matches the reported hectares.
    """
    v = np.nan_to_num(dist, nan=0.0)
    lo = np.nanpercentile(dist[changed], 5) if changed.any() else 0.0
    hi = np.nanpercentile(dist[changed], 99) if changed.any() else 1.0
    t = np.clip((v - lo) / max(hi - lo, 1e-6), 0, 1)
    rgba = np.zeros((4, *dist.shape), np.uint8)
    rgba[0] = (90 + 165 * t).astype(np.uint8)    # #5aa9ff → white
    rgba[1] = (169 + 86 * t).astype(np.uint8)
    rgba[2] = 255
    rgba[3] = np.where(changed, 200, 0).astype(np.uint8)
    _write_png(path, rgba)
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

