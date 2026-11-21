"""A target pixel grid. Every band from every sensor gets resampled onto one of these, so tools
never have to care about native tiling, projection or pixel size."""

from __future__ import annotations

import math
from dataclasses import dataclass

from rasterio.transform import Affine, from_origin
from rasterio.warp import transform_bounds

from ..aoi import BBox


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

    def corners_lonlat(self) -> list[list[float]]:
        """Top-left, top-right, bottom-right, bottom-left in lon/lat (for map image overlays)."""
        from rasterio.warp import transform

        t = self.transform
        xs, ys = zip(*(t @ (c, r) for c, r in
                       ((0, 0), (self.width, 0), (self.width, self.height), (0, self.height))))
        lons, lats = transform(self.crs, "EPSG:4326", list(xs), list(ys))
        return [[round(lo, 6), round(la, 6)] for lo, la in zip(lons, lats)]

    def key(self) -> str:
        t = self.transform
        return f"{self.crs}|{t.a:.3f}|{t.c:.1f}|{t.f:.1f}|{self.width}x{self.height}"


def utm_crs(bbox: BBox) -> str:
    """WGS84 / UTM zone containing the box centre (EPSG:326zz north, 327zz south), so pixels
    keep their true size anywhere on Earth. Norway/Svalbard zone exceptions are ignored: the
    neighbouring zone is still accurate enough for a box this small."""
    w, s, e, n = bbox
    lon, lat = (w + e) / 2, (s + n) / 2
    lon = (lon + 180) % 360 - 180
    zone = min(int((lon + 180) // 6) + 1, 60)
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def grid_for(bbox: BBox, res_m: float, crs: str | None = None) -> Grid:
    """Snap a lon/lat bbox to a grid of ``res_m`` pixels in ``crs`` (default: the box's own
    UTM zone), with pixel edges on multiples of res."""
    crs = crs or utm_crs(bbox)
    w, s, e, n = transform_bounds("EPSG:4326", crs, *bbox, densify_pts=21)
    w = math.floor(w / res_m) * res_m
    s = math.floor(s / res_m) * res_m
    e = math.ceil(e / res_m) * res_m
    n = math.ceil(n / res_m) * res_m
    width = round((e - w) / res_m)
    height = round((n - s) / res_m)
    return Grid(crs, from_origin(w, n, res_m, res_m), width, height)
