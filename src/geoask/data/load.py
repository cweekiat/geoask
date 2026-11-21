"""Load bands for a date onto a grid, by wavelength, with cloud masking and tile mosaicking."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from rasterio.enums import Resampling

from ..profiles import Band
from .cog import read_to_grid
from .grid import Grid
from .stac import Scene


@dataclass
class Stack:
    """Bands for one date on one grid. Values are physical units (reflectance or linear gamma0)."""

    date: str
    grid: Grid
    bands: dict[str, np.ndarray]  # keyed by the requested target (e.g. "red", "vv")
    valid: np.ndarray  # bool: has data and isn't cloud/shadow
    scenes: list[str] = field(default_factory=list)
    sensor: str = ""

    @property
    def clear_fraction(self) -> float:
        return float(self.valid.mean()) if self.valid.size else 0.0


def _band_for(scene: Scene, target: str) -> Band:
    p = scene.profile
    if p.modality == "sar":
        return p.polarization(target)
    return p.band_near(target)


def load_stack(scenes: list[Scene], targets: list[str], grid: Grid) -> Stack:
    """Mosaic same-date ``scenes`` onto ``grid``. ``targets`` are wavelength names or polarisations.

    Later scenes fill pixels the earlier ones left empty or cloudy.
    """
    if not scenes:
        raise ValueError("no scenes")
    out = {t: np.full(grid.shape, np.nan, np.float32) for t in targets}
    valid = np.zeros(grid.shape, bool)
    for sc in scenes:
        p = sc.profile
        ok = np.ones(grid.shape, bool)
        if p.cloud_mask is not None and p.cloud_mask.asset in sc.item.assets:
            scl = read_to_grid(sc.href(p.cloud_mask.asset), grid, Resampling.nearest)
            ok &= ~np.isnan(scl) & ~np.isin(scl, p.cloud_mask.invalid)
        fill = ok & ~valid
        if not fill.any():
            continue
        for t in targets:
            b = _band_for(sc, t)
            raw = read_to_grid(sc.href(b.asset), grid, Resampling.bilinear, nodata=p.nodata)
            phys = raw * b.scale + b.offset
            ok_t = ~np.isnan(phys)
            sel = fill & ok_t
            out[t][sel] = phys[sel]
            fill &= ok_t
        valid |= fill
    for t in targets:
        out[t][~valid] = np.nan
    return Stack(
        date=scenes[0].date,
        grid=grid,
        bands=out,
        valid=valid,
        scenes=[s.id for s in scenes],
        sensor=scenes[0].profile.id,
    )
