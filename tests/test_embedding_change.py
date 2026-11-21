import numpy as np

from geoask.models.base import Embeddings
from geoask.tools.embedding_change import otsu_threshold, patch_distance_map, upsample


def _emb(patches, origins, shape=(300, 260)):
    n = len(patches)
    return Embeddings("m", "1", np.zeros((n, 4), np.float32), [(0, 0, 1, 1)] * n, "EPSG:32648",
                      "d", np.ones(n), patches, origins, shape, 256)


def test_patch_distances_mosaic_and_overlap():
    rng = np.random.default_rng(0)
    a = rng.normal(size=(2, 32, 32, 16)).astype(np.float32)
    b = a.copy()
    b[1, 28:, 28:] = -b[1, 28:, 28:]  # flip chip 2 where it does not overlap chip 1 -> 2
    pm, step = patch_distance_map(_emb(a, [(0, 0), (44, 4)]), _emb(b, [(0, 0), (44, 4)]))
    assert step == 8 and pm.shape == (38, 33)
    assert np.nanmax(pm) > 1.9 and np.nanmin(pm) < 1e-5
    assert upsample(pm, step, (300, 260)).shape == (300, 260)


def test_otsu_splits_two_populations():
    d = np.concatenate([np.full(900, 0.2), np.full(100, 0.9)]) + np.random.default_rng(1).normal(0, .03, 1000)
    t = otsu_threshold(d)
    assert 0.3 < t < 0.8


def test_refuses_mixed_models():
    a = np.zeros((1, 32, 32, 4), np.float32)
    e0, e1 = _emb(a, [(0, 0)]), _emb(a, [(0, 0)])
    e1.model_id = "other"
    try:
        patch_distance_map(e0, e1)
    except ValueError:
        return
    raise AssertionError("mixed models were compared")
