"""Offline tests never touch the online geocoder: a small fake stands in for it."""

import pytest

from geoask import geocode

FAKE = {
    "paris": [{"name": "Paris, Île-de-France, France", "short": "Paris",
               "bbox": [2.22410, 48.81557, 2.46977, 48.90216], "kind": "boundary/administrative"}],
    "lisbon": [{"name": "Lisbon, Portugal", "short": "Lisbon",
                "bbox": [-9.16, 38.70, -9.12, 38.73], "kind": "place/city"}],
}


@pytest.fixture(autouse=True)
def fake_geocoder(monkeypatch, request):
    if request.node.get_closest_marker("network"):
        return
    monkeypatch.setattr(geocode, "lookup",
                        lambda name, limit=5, timeout=8: FAKE.get(name.strip().lower(), [])[:limit])
