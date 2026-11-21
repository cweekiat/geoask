"""Pick the best acquisition date for an area.

1. Rank every date by clear pixels *inside the area* using the sensor's own mask (cheap: read at a
   coarse grid, from COG overviews).
2. Re-check the top candidates with an independent spectral haze test (``data.clouds``) and pick
   the one with the most clear-and-haze-free pixels. Vendor masks alone aren't trusted.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np
from rasterio.enums import Resampling

from ..aoi import BBox
from ..data.clouds import TEST_TARGETS, potential_cloud
from ..data.cog import read_to_grid
from ..data.grid import grid_for
from ..data.load import load_stack
from ..data.stac import Scene, group_by_date

RANK_RES_M = 60
RECHECK_TOP = 6


@dataclass
class DateCandidate:
    date: str
    scenes: list[Scene]
    clear_fraction: float  # by the sensor's own mask
    haze_fraction: float | None = None  # flagged by the spectral test (None = not checked)

    @property
    def score(self) -> float:
        return self.clear_fraction - (self.haze_fraction or 0.0)


def rank_dates(scenes: list[Scene], bbox: BBox) -> list[DateCandidate]:
    grid = grid_for(bbox, RANK_RES_M)

    def score(item: tuple[str, list[Scene]]) -> DateCandidate:
        date, group = item
        p = group[0].profile
        if p.cloud_mask is None:
            return DateCandidate(date, group, 1.0)
        valid = np.zeros(grid.shape, bool)
        for sc in group:
            if p.cloud_mask.asset not in sc.item.assets:
                continue
            scl = read_to_grid(sc.href(p.cloud_mask.asset), grid, Resampling.nearest)
            valid |= ~np.isnan(scl) & ~np.isin(scl, p.cloud_mask.invalid)
        return DateCandidate(date, group, float(valid.mean()))

    with ThreadPoolExecutor(max_workers=12) as ex:  # one HTTP-bound read per date
        out = list(ex.map(score, group_by_date(scenes).items()))
    return sorted(out, key=lambda c: c.clear_fraction, reverse=True)


def recheck_haze(cands: list[DateCandidate], bbox: BBox) -> list[DateCandidate]:
    grid = grid_for(bbox, RANK_RES_M)
    for c in cands:
        prof = c.scenes[0].profile
        if prof.modality != "optical" or not all(prof.has(t) for t in TEST_TARGETS):
            continue
        st = load_stack(c.scenes, list(TEST_TARGETS), grid)
        flagged = potential_cloud(st.bands) & st.valid
        c.haze_fraction = float(flagged.mean())
    return sorted(cands, key=lambda c: c.score, reverse=True)


def best_date(scenes: list[Scene], bbox: BBox, min_clear: float = 0.0) -> DateCandidate | None:
    ranked = [c for c in rank_dates(scenes, bbox) if c.clear_fraction >= min_clear]
    if not ranked:
        return None
    return recheck_haze(ranked[:RECHECK_TOP], bbox)[0]
