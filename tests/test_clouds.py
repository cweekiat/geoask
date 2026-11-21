import numpy as np

from geoask.data.clouds import potential_cloud


def _px(blue, green, red, nir, swir2):
    return {k: np.array([v], np.float32) for k, v in
            zip(("blue", "green", "red", "nir", "swir2"), (blue, green, red, nir, swir2))}


def test_haze_over_sea_is_flagged():  # values seen over the strait on 2026-03-25
    assert potential_cloud(_px(0.30, 0.30, 0.31, 0.38, 0.40))[0]


def test_clear_water_vegetation_and_soil_are_not():
    assert not potential_cloud(_px(0.09, 0.086, 0.05, 0.02, 0.01))[0]  # turbid sea
    assert not potential_cloud(_px(0.03, 0.06, 0.03, 0.35, 0.08))[0]  # forest
    assert not potential_cloud(_px(0.10, 0.15, 0.20, 0.25, 0.30))[0]  # red earth
