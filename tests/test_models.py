import numpy as np
import pytest

from geoask.data.grid import grid_for
from geoask.data.load import Stack
from geoask.models import ModelNotInstalled, SensorNotSupported, get, list_models
from geoask.profiles import load_profile, profile_from_stac_item


def _s2_stack(seed=0):
    p = load_profile("sentinel-2-l2a")
    g = grid_for((103.72, 1.35, 103.733, 1.363), 10)
    rng = np.random.default_rng(seed)
    bands = {b.name: rng.uniform(0.01, 0.4, g.shape).astype(np.float32) for b in p.bands}
    return Stack("2026-01-01", g, bands, np.ones(g.shape, bool), ["x"], p.id), p


def test_registry_lists_known_models():
    ids = {s.id for s in list_models()}
    assert {"spectral-baseline", "clay-v1.5", "prithvi-eo-2.0", "dofa", "terramind-1.0"} <= ids


def test_baseline_embeds_any_optical_sensor():
    stack, prof = _s2_stack()
    emb = get("spectral-baseline").embed_stack(stack, prof)
    assert emb.vectors.ndim == 2 and len(emb.chip_bounds) == emb.vectors.shape[0] > 0
    assert emb.model_id == "spectral-baseline"
    assert np.allclose(emb.cosine_to(emb), 0, atol=1e-5)


def test_fixed_band_model_maps_by_wavelength_or_refuses():
    prithvi = get("prithvi-eo-2.0")
    s2 = load_profile("sentinel-2-l2a")
    assert prithvi.select_bands(s2) == ["blue", "green", "red", "nir08", "swir16", "swir22"]
    assert not prithvi.supports(load_profile("sentinel-1-rtc"))
    rgb_only = profile_from_stac_item({"properties": {}, "assets": {
        k: {"eo:bands": [{"name": k, "center_wavelength": w}]}
        for k, w in (("r", 0.66), ("g", 0.56), ("b", 0.49))}})
    with pytest.raises(SensorNotSupported):
        prithvi.select_bands(rgb_only)


def test_planned_models_say_so():
    with pytest.raises(ModelNotInstalled):
        get("clay-v1.5").load()


def test_embeddings_from_different_models_never_mix():
    stack, prof = _s2_stack()
    a = get("spectral-baseline").embed_stack(stack, prof)
    b = get("spectral-baseline").embed_stack(stack, prof)
    b.model_id = "other"
    with pytest.raises(ValueError):
        a.cosine_to(b)
