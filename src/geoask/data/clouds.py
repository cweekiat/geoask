"""Sensor-agnostic spectral cloud/haze test, used alongside a sensor's own mask.

Vendor masks miss things: Sen2Cor's SCL labels bright haze over the Singapore Strait as "water"
or "not vegetated". This test uses only wavelengths, so it works for any optical sensor with
blue/green/red/NIR/SWIR2.

Based on the potential-cloud tests of Fmask (Zhu & Woodcock 2012), without the thermal band:
  * HOT (haze-optimised transform):  blue − 0.5·red − 0.08 > 0
  * whiteness: Σ|vis − mean(vis)| / mean(vis) < 0.7
  * basic:      SWIR2 > 0.03 and NDVI < 0.8
Bright white roofs and concrete also pass, so GeoAsk uses the *share* of flagged pixels to rank
dates (roofs are constant between dates; haze isn't), rather than masking pixels with it.
"""

from __future__ import annotations

import numpy as np

TEST_TARGETS = ("blue", "green", "red", "nir", "swir2")


def potential_cloud(b: dict[str, np.ndarray]) -> np.ndarray:
    blue, green, red, nir, swir2 = (b[k] for k in TEST_TARGETS)
    vis = np.stack([blue, green, red])
    mean = vis.mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        white = np.abs(vis - mean).sum(axis=0) / mean
        ndvi = (nir - red) / (nir + red)
    hot = blue - 0.5 * red - 0.08
    out = (hot > 0) & (white < 0.7) & (swir2 > 0.03) & (ndvi < 0.8)
    return out & ~np.isnan(mean)
