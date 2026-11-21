import numpy as np

from geoask.detect import Box, merge_boxes, slice_windows, sliced_detect
from geoask.detect.sar_vessels import SarVesselCFAR
from geoask.tools.activity import fixed_targets, robust_anomalies


def test_slices_cover_the_image_with_overlap():
    wins = slice_windows(1000, 700, size=512, overlap=0.2)
    cover = np.zeros((1000, 700), int)
    for y0, x0, y1, x1 in wins:
        assert y1 - y0 == 512 and x1 - x0 == 512
        cover[y0:y1, x0:x1] += 1
    assert cover.min() >= 1
    assert slice_windows(100, 80, 512) == [(0, 0, 100, 80)]


def test_merge_rejoins_a_box_split_by_a_slice_edge():
    a, b = Box(0, 0, 10, 4, 0.9, "vessel"), Box(8, 0, 20, 4, 0.7, "vessel")
    far = Box(100, 100, 110, 104, 0.8, "vessel")
    out = merge_boxes([a, b, far], match=0.15)
    assert len(out) == 2 and any(m.x0 == 0 and m.x1 == 20 for m in out)
    assert len(merge_boxes([a, Box(8, 0, 20, 4, 0.7, "other")])) == 2  # labels never merge


def _sea(h=600, w=900, seed=0):
    rng = np.random.default_rng(seed)
    vv = rng.gamma(4.0, 0.01 / 4.0, (h, w)).astype(np.float32)  # speckled sea, about -20 dB
    vv[:, :120] = rng.gamma(4.0, 0.3 / 4.0, (h, 120))  # land on the left
    return vv


def test_cfar_finds_small_and_large_ships_but_not_land():
    vv = _sea()
    vv[100:103, 400:404] = 3.0  # small vessel, 30-40 m
    vv[300:306, 500:540] = 300.0  # large ship, 400 m
    vv[300:306, 480:560] += 0.3  # its range sidelobe
    vv[500:503, 700:703] = 2.0
    boxes = sliced_detect({"vv": vv}, SarVesselCFAR(), size=512, overlap=0.2)
    centres = sorted((round((b.y0 + b.y1) / 2), round((b.x0 + b.x1) / 2)) for b in boxes)
    assert len(boxes) == 3, centres
    assert all(b.x0 > 120 for b in boxes)
    big = max(boxes, key=lambda b: b.area)
    assert big.x1 - big.x0 < 60  # sidelobe not swallowed into the box


def test_anomalies_and_fixed_targets():
    med, _sd, idx = robust_anomalies([40, 42, 38, 41, 90, 39])
    assert med == 40.5 and idx == [4]
    assert robust_anomalies([5, 5, 5, 6])[2] == []  # sd floor: one vessel isn't unusual
    pts = [{"date": f"d{i}", "lon": 103.8, "lat": 1.2} for i in range(5)]  # beacon on every pass
    pts += [{"date": "d0", "lon": 103.81, "lat": 1.21}]
    assert len(fixed_targets(pts, passes=5)) == 1
