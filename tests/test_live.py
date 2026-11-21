"""Hits the real open-data buckets. Run with: pytest -m network"""

import pytest

from geoask import aoi
from geoask.data.grid import grid_for
from geoask.data.load import load_stack
from geoask.data.stac import find_scenes
from geoask.profiles import load_profile


@pytest.mark.network
def test_sentinel2_reflectance_is_physical():
    p = load_profile("sentinel-2-l2a")
    bbox = aoi.resolve("tengah").bbox
    scenes = [s for s in find_scenes(p, bbox, "2026-03-25", "2026-03-26")]
    assert scenes
    st = load_stack(scenes, ["red", "nir"], grid_for((103.725, 1.36, 103.735, 1.37), 10))
    import numpy as np

    red = np.nanmedian(st.bands["red"])
    assert 0.0 < red < 0.08  # forest red reflectance; a double-applied offset goes negative
