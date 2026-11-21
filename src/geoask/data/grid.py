"""A target pixel grid. Every band from every sensor gets resampled onto one of these, so tools
never have to care about native tiling, projection or pixel size."""

from __future__ import annotations

import math
from dataclasses import dataclass

from rasterio.transform import Affine, from_origin
from rasterio.warp import transform_bounds

from ..aoi import SINGAPORE_UTM, BBox


@dataclass(frozen=True)
class Grid:
    crs: str
    transform: Affine
    width: int
    height: int

    @property
    def res(self) -> float:
        return self.transform.a

    @property
    def pixel_area_m2(self) -> float:
        return self.transform.a * -self.transform.e

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def key(self) -> str:
        t = self.transform
        return f"{self.crs}|{t.a:.3f}|{t.c:.1f}|{t.f:.1f}|{self.width}x{self.height}"


def grid_for(bbox: BBox, res_m: float, crs: str = SINGAPORE_UTM) -> Grid:
    """Snap a lon/lat bbox to a grid of ``res_m`` pixels in ``crs`` (pixel edges on multiples of res)."""
    w, s, e, n = transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
    w = math.floor(w / res_m) * res_m
    s = math.floor(s / res_m) * res_m
    e = math.ceil(e / res_m) * res_m
    n = math.ceil(n / res_m) * res_m
    width = round((e - w) / res_m)
    height = round((n - s) / res_m)
    return Grid(crs, from_origin(w, n, res_m, res_m), width, height)
