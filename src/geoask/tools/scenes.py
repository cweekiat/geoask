"""Pick the best acquisition date for an area, ranked by clear pixels *inside the area*."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rasterio.enums import Resampling

from ..aoi import BBox
from ..data.cog import read_to_grid
from ..data.grid import grid_for
from ..data.stac import Scene, group_by_date

RANK_RES_M = 60  # rank on a coarse grid: the cloud mask is cheap to read at overview level


@dataclass
class DateCandidate:
    date: str
    scenes: list[Scene]
    clear_fraction: float


def rank_dates(scenes: list[Scene], bbox: BBox) -> list[DateCandidate]:
    grid = grid_for(bbox, RANK_RES_M)
    out = []
    for date, group in group_by_date(scenes).items():
        p = group[0].profile
        if p.cloud_mask is None:
            out.append(DateCandidate(date, group, 1.0))  # e.g. SAR: weather doesn't matter
            continue
        valid = np.zeros(grid.shape, bool)
        for sc in group:
            if p.cloud_mask.asset not in sc.item.assets:
                continue
            scl = read_to_grid(sc.href(p.cloud_mask.asset), grid, Resampling.nearest)
            valid |= ~np.isnan(scl) & ~np.isin(scl, p.cloud_mask.invalid)
        out.append(DateCandidate(date, group, float(valid.mean())))
    return sorted(out, key=lambda c: c.clear_fraction, reverse=True)


def best_date(scenes: list[Scene], bbox: BBox, min_clear: float = 0.0) -> DateCandidate | None:
    ranked = rank_dates(scenes, bbox)
    return ranked[0] if ranked and ranked[0].clear_fraction >= min_clear else None
