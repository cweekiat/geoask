"""Offline tests never touch the online geocoder: a small fake stands in for it."""

import pytest

from geoask import geocode

FAKE = {
    "paris": [{"name": "Paris, Île-de-France, France", "short": "Paris",
               "bbox": [2.22410, 48.81557, 2.46977, 48.90216], "kind": "boundary/administrative"}],
    "lisbon": [{"name": "Lisbon, Portugal", "short": "Lisbon",
                "bbox": [-9.16, 38.70, -9.12, 38.73], "kind": "place/city"}],
    "tesla gigafactory berlin": [{"name": "Tesla Gigafactory Berlin-Brandenburg", "short":
                                  "Tesla Gigafactory Berlin-Brandenburg", "kind": "landuse/industrial",
                                  "bbox": [13.78674, 52.38942, 13.81498, 52.40504]}],
    "bay of gibraltar": [{"name": "Bay of Gibraltar", "short": "Bay of Gibraltar", "kind": "natural/bay",
                          "bbox": [-5.44726, 36.07704, -5.34609, 36.18149]}],
    "zermatt": [{"name": "Zermatt", "short": "Zermatt", "kind": "boundary/administrative",
                 "bbox": [7.57499, 45.91675, 7.90868, 46.06433]}],
    "sydney opera house": [{"name": "Sydney Opera House", "short": "Sydney Opera House",
                            "kind": "amenity/theatre", "bbox": [151.20971, -33.86172, 151.22053, -33.85268]}],
}


@pytest.fixture(autouse=True)
def fake_geocoder(monkeypatch, request):
    if request.node.get_closest_marker("network"):
        return
    monkeypatch.setattr(geocode, "lookup",
                        lambda name, limit=5, timeout=8: FAKE.get(name.strip().lower(), [])[:limit])
