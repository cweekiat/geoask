"""Vessels on Sentinel-1 radar by CFAR (constant false alarm rate): the standard, weight-free SAR
ship detector. Works day and night through cloud, anywhere there is open water.

A pixel is a target if it is much brighter than the sea around it: VV backscatter above
``k`` standard deviations of a local background ring (guard band excluded), on pixels whose
surroundings are water. Clusters of target pixels become one box. At 10 m pixels, vessels shorter
than about 20–30 m are often missed, and moored ships touching piers merge with the land.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .base import Box


class SarVesselCFAR:
    id = "sar-vessel-cfar"
    labels = ("vessel",)
    min_object_px = 2

    def __init__(self, k: float = 5.0, background: int = 81, guard: int = 41,
                 water_db: float = -16.0, min_px: int = 4, max_px: int = 6000, min_db: float = -12.0,
                 land_px: int = 2000, lobe_db: float = 12.0, peak_db: float = -5.0):
        self.k, self.bg, self.guard = k, background, guard
        self.water_db, self.min_px, self.max_px, self.min_db = water_db, min_px, max_px, min_db
        self.land_px, self.lobe_db, self.peak_db = land_px, lobe_db, peak_db

    def water_mask(self, vv: np.ndarray) -> np.ndarray:
        """Open water: everything except large bright regions (land), with land grown by 3 pixels
        so piers and shorelines don't count as targets."""
        db = 10 * np.log10(np.clip(np.nan_to_num(vv, nan=1.0), 1e-6, None))
        bright = ndimage.median_filter(db, size=15) >= self.water_db
        # A big ship and its sidelobes can look bright even in the median; land is only the
        # *large* bright regions (> land_px, 0.2 km² at 10 m), so ships stay on the water.
        lab, n = ndimage.label(bright)
        if n:
            sizes = ndimage.sum_labels(bright, lab, index=np.arange(1, n + 1))
            land = np.isin(lab, np.flatnonzero(sizes > self.land_px) + 1)
        else:
            land = bright
        land = ndimage.binary_dilation(land, iterations=3)
        return ~land & ~np.isnan(vv)

    def detect(self, chip: dict[str, np.ndarray]) -> list[Box]:
        vv = chip["vv"].astype(np.float64)
        water = self.water_mask(vv)
        if water.sum() < 200:
            return []
        db = 10 * np.log10(np.clip(np.nan_to_num(vv, nan=1e-6), 1e-6, None))
        # Censored CFAR: bright candidates (and their sidelobes) are left out of the sea statistics,
        # so a large ship or a crowded anchorage doesn't raise its own threshold.
        cand = water & (db > self.min_db)
        sea = water & ~ndimage.binary_dilation(cand, iterations=4)
        x = np.where(sea, np.nan_to_num(vv), 0.0)
        w = sea.astype(np.float64)

        def box_sum(a: np.ndarray, n: int) -> np.ndarray:
            return ndimage.uniform_filter(a, size=n, mode="constant") * n * n

        n_bg = box_sum(w, self.bg) - box_sum(w, self.guard)
        s_bg = box_sum(x, self.bg) - box_sum(x, self.guard)
        s2_bg = box_sum(x * x, self.bg) - box_sum(x * x, self.guard)
        enough = n_bg > 0.2 * (self.bg**2 - self.guard**2)
        n_bg = np.maximum(n_bg, 1)
        mu = s_bg / n_bg
        sd = np.sqrt(np.maximum(s2_bg / n_bg - mu * mu, 1e-12))
        # Sidelobes: a bright ship smears a cross of fainter returns that would join neighbours
        # into one blob. Keep only pixels within ``lobe_db`` of the brightest return nearby.
        near_peak = db >= ndimage.maximum_filter(db, size=61) - self.lobe_db
        hit = cand & enough & near_peak & (vv > mu + self.k * sd)
        lab, _ = ndimage.label(ndimage.binary_closing(hit, iterations=1))
        boxes = []
        for i, sl in enumerate(ndimage.find_objects(lab), start=1):
            if sl is None:
                continue
            px = int((lab[sl] == i).sum())
            if not self.min_px <= px <= self.max_px:
                continue
            peak = float(np.nanmax(np.where(lab[sl] == i, vv[sl], np.nan)))
            if 10 * np.log10(max(peak, 1e-6)) < self.peak_db:
                continue  # too faint to tell from sea clutter
            score = float(np.clip((peak - mu[sl].mean()) / (self.k * sd[sl].mean() + 1e-12) / 3, 0, 1))
            boxes.append(Box(sl[1].start, sl[0].start, sl[1].stop, sl[0].stop, score, "vessel"))
        return boxes
