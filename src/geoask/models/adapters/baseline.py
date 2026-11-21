"""A model-free baseline encoder: per-chip spectral statistics.

It runs today with no weights, works with any sensor (it picks bands by wavelength), and gives every
GFM a floor to beat in the benchmarks.
"""

from __future__ import annotations

import numpy as np

from ...profiles import WAVELENGTHS
from ..base import GeoEncoder, ModelInput, ModelSpec
from ..registry import register

_TARGETS = ("blue", "green", "red", "nir", "swir1", "swir2")


@register
class SpectralBaseline(GeoEncoder):
    spec = ModelSpec(
        id="spectral-baseline",
        family="Baseline",
        description="Per-chip band means/stds plus NDVI, MNDWI and NDBI stats. No weights.",
        modalities=("optical", "sar"),
        bands="any",
        chip_size=64,
        license="MIT",
        integrated=True,
    )
    version = "1"

    def _embed(self, inputs: ModelInput):
        px = inputs.pixels  # (N, C, H, W), NaN = missing
        wl = inputs.wavelengths_um
        feats = []
        if wl.max() > 100:  # SAR: wavelengths in cm range -> log backscatter stats
            db = 10 * np.log10(np.clip(px, 1e-6, None))
            feats += [np.nanmean(db, axis=(2, 3)), np.nanstd(db, axis=(2, 3))]
        else:
            idx = {t: int(np.argmin(np.abs(wl - WAVELENGTHS[t]))) for t in _TARGETS
                   if np.min(np.abs(wl - WAVELENGTHS[t])) < 0.1}
            sel = [idx[t] for t in _TARGETS if t in idx]
            feats += [np.nanmean(px[:, sel], axis=(2, 3)), np.nanstd(px[:, sel], axis=(2, 3))]

            def nd(a, b):
                if a not in idx or b not in idx:
                    return None
                x, y = px[:, idx[a]], px[:, idx[b]]
                with np.errstate(divide="ignore", invalid="ignore"):
                    v = (x - y) / (x + y)
                return np.stack([np.nanmean(v, axis=(1, 2)), np.nanstd(v, axis=(1, 2))], axis=1)

            for pair in (("nir", "red"), ("green", "swir1"), ("swir1", "nir")):
                if (v := nd(*pair)) is not None:
                    feats.append(v)
        return np.nan_to_num(np.concatenate(feats, axis=1)), None
