import pytest

from geoask.profiles import BandNotAvailable, load_profile, profile_from_stac_item


def test_band_lookup_by_wavelength():
    p = load_profile("sentinel-2-l2a")
    assert p.band_near("red").asset == "red"
    assert p.band_near("nir").asset == "nir"
    assert p.band_near("swir1").asset == "swir16"
    assert p.band_near(0.86).asset == "nir08"


def test_missing_band_is_refused_not_guessed():
    # A sensor with only green + NIR must not pass red-edge off as red.
    item = {
        "collection": "toy",
        "properties": {},
        "assets": {
            "g": {"eo:bands": [{"name": "g", "center_wavelength": 0.56}], "gsd": 5},
            "re": {"eo:bands": [{"name": "re", "center_wavelength": 0.74}], "gsd": 5},
        },
    }
    p = profile_from_stac_item(item)
    assert p.band_near("green").asset == "g"
    with pytest.raises(BandNotAvailable):
        p.band_near("red")
    assert p.gsd_m == 5


def test_sar_profile():
    p = load_profile("sentinel-1-rtc")
    assert p.modality == "sar"
    assert p.polarization("vh").asset == "vh"
    with pytest.raises(BandNotAvailable):
        p.band_near("red")


def _item(offset, baked):
    return {
        "properties": {"earthsearch:boa_offset_applied": baked},
        "assets": {
            b.asset: {"raster:bands": [{"scale": 0.0001, "offset": offset}]}
            for b in load_profile("sentinel-2-l2a").bands
        },
    }


def test_offset_from_item_unless_already_applied():
    p = load_profile("sentinel-2-l2a")
    assert p.with_item(_item(-0.1, False)).band_near("red").offset == -0.1
    assert p.with_item(_item(-0.1, True)).band_near("red").offset == 0.0
