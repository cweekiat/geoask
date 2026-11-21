from geoask.data.grid import grid_for, utm_crs


def test_utm_zone_follows_the_area():
    assert utm_crs((103.7, 1.3, 103.8, 1.4)) == "EPSG:32648"      # Singapore
    assert utm_crs((-9.16, 38.70, -9.12, 38.73)) == "EPSG:32629"  # Lisbon
    assert utm_crs((151.1, -33.9, 151.3, -33.8)) == "EPSG:32756"  # Sydney, southern hemisphere
    assert utm_crs((-179.9, 0, -179.8, 0.1)) == "EPSG:32601"


def test_grid_pixels_are_true_size_anywhere():
    g = grid_for((-9.16, 38.70, -9.12, 38.73), 10)
    assert g.crs == "EPSG:32629" and g.res == 10
    assert 330 < g.width < 360 and 320 < g.height < 345  # ~3.5 km x ~3.3 km
