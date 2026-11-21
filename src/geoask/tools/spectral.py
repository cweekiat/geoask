"""Spectral indices defined by wavelength, so they work on any optical sensor with the bands.

Every number returned comes from native-resolution pixels. Super-resolved pixels never feed these.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..data.load import Stack

# index name -> (a, b) wavelength targets; index = (a - b) / (a + b)
INDICES: dict[str, tuple[str, str]] = {
    "ndvi": ("nir", "red"),  # vegetation
    "ndwi": ("green", "nir"),  # open water (McFeeters)
    "mndwi": ("green", "swir1"),  # water, better in built-up areas (Xu)
    "ndbi": ("swir1", "nir"),  # built-up / bare
}


def targets_for(*names: str) -> list[str]:
    t: list[str] = []
    for n in names:
        for w in INDICES[n]:
            if w not in t:
                t.append(w)
    return t


def compute(stack: Stack, name: str) -> np.ndarray:
    a_key, b_key = INDICES[name]
    a, b = stack.bands[a_key], stack.bands[b_key]
    with np.errstate(divide="ignore", invalid="ignore"):
        idx = (a - b) / (a + b)
    idx[~stack.valid] = np.nan
    return np.clip(idx, -1, 1)


@dataclass
class ChangeResult:
    index: str
    date0: str
    date1: str
    mean0: float
    mean1: float
    loss_ha: float  # pixels that crossed from >= hi to <= lo
    gain_ha: float
    compared_fraction: float  # share of the area valid on both dates
    area_ha: float
    sensor: str
    scenes0: list[str]
    scenes1: list[str]
    delta: np.ndarray  # index1 - index0, NaN where not comparable
    loss: np.ndarray  # bool: counted in loss_ha
    gain: np.ndarray  # bool: counted in gain_ha

    def summary(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("delta", "loss", "gain")}
        for k in ("mean0", "mean1", "loss_ha", "gain_ha", "compared_fraction", "area_ha"):
            d[k] = round(d[k], 3)
        return d


THRESHOLDS = {"ndvi": (0.5, 0.3), "ndwi": (0.2, 0.0), "mndwi": (0.2, 0.0), "ndbi": (0.1, -0.1)}


def change(s0: Stack, s1: Stack, name: str) -> ChangeResult:
    i0, i1 = compute(s0, name), compute(s1, name)
    both = ~np.isnan(i0) & ~np.isnan(i1)
    hi, lo = THRESHOLDS[name]
    px_ha = s0.grid.pixel_area_m2 / 10_000
    loss = both & (i0 >= hi) & (i1 <= lo)
    gain = both & (i0 <= lo) & (i1 >= hi)
    delta = np.where(both, i1 - i0, np.nan).astype(np.float32)
    return ChangeResult(
        index=name,
        date0=s0.date,
        date1=s1.date,
        mean0=float(np.nanmean(i0[both])) if both.any() else float("nan"),
        mean1=float(np.nanmean(i1[both])) if both.any() else float("nan"),
        loss_ha=float(loss.sum() * px_ha),
        gain_ha=float(gain.sum() * px_ha),
        compared_fraction=float(both.mean()),
        area_ha=float(both.size * px_ha),
        sensor=s0.sensor,
        scenes0=s0.scenes,
        scenes1=s1.scenes,
        delta=delta,
        loss=loss,
        gain=gain,
    )
