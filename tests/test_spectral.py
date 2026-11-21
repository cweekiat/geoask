import numpy as np

from geoask.data.grid import grid_for
from geoask.data.load import Stack
from geoask.tools import spectral


def _stack(red, nir, date):
    g = grid_for((103.72, 1.35, 103.7202, 1.3502), 10)
    shape = g.shape
    bands = {"red": np.full(shape, red, np.float32), "nir": np.full(shape, nir, np.float32)}
    return Stack(date, g, bands, np.ones(shape, bool), ["s"], "test")


def test_grid_snaps_to_resolution():
    g = grid_for((103.72, 1.35, 103.73, 1.36), 10)
    assert g.transform.c % 10 == 0 and g.transform.f % 10 == 0
    assert g.res == 10


def test_ndvi_and_loss_area():
    forest = _stack(0.03, 0.35, "2019-01-01")  # ndvi ~0.84
    cleared = _stack(0.20, 0.25, "2025-01-01")  # ndvi ~0.11
    r = spectral.change(forest, cleared, "ndvi")
    px = forest.valid.size * forest.grid.pixel_area_m2 / 10_000
    assert abs(r.mean0 - (0.32 / 0.38)) < 1e-4
    assert r.loss_ha == px and r.gain_ha == 0
    assert r.compared_fraction == 1.0


def test_invalid_pixels_excluded():
    a, b = _stack(0.03, 0.35, "a"), _stack(0.2, 0.25, "b")
    b.valid[:] = False
    r = spectral.change(a, b, "ndvi")
    assert r.compared_fraction == 0 and r.loss_ha == 0
