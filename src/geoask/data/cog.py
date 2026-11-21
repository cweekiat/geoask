"""Read just the pixels you need from a Cloud-Optimized GeoTIFF, onto a target grid.

GDAL fetches only the internal tiles (and overview level) that intersect the window, via HTTP
range requests. No keys: public buckets are read unsigned.
"""

from __future__ import annotations

import os

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from .cache import WindowCache
from .grid import Grid

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MULTIPLEX": "YES",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "VSI_CACHE": "TRUE",
    "AWS_NO_SIGN_REQUEST": "YES",
}

_cache: WindowCache | None = None


def _get_cache() -> WindowCache | None:
    global _cache
    if os.environ.get("GEOASK_NO_CACHE"):
        return None
    if _cache is None:
        _cache = WindowCache()
    return _cache


def read_to_grid(
    href: str,
    grid: Grid,
    resampling: Resampling = Resampling.bilinear,
    band: int = 1,
    nodata: float | None = None,
) -> np.ndarray:
    """Return band ``band`` of ``href`` warped onto ``grid`` as float32 (NaN where no data)."""
    key = f"{href}|{band}|{resampling.name}|{grid.key()}"
    cache = _get_cache()
    if cache is not None and (hit := cache.get(key)) is not None:
        return hit
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        nd = nodata if nodata is not None else src.nodata
        with WarpedVRT(
            src,
            crs=grid.crs,
            transform=grid.transform,
            width=grid.width,
            height=grid.height,
            resampling=resampling,
            src_nodata=nd,
            nodata=nd,
        ) as vrt:
            arr = vrt.read(band, out_dtype="float32")
    if nd is not None:
        arr[arr == nd] = np.nan
    if cache is not None:
        cache.put(key, arr)
    return arr
