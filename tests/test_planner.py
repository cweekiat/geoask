from datetime import date

import pytest

from geoask import aoi
from geoask.agent.planner import Clarify, Plan, RuleBasedPlanner, windows

P = RuleBasedPlanner()
TODAY = date(2026, 11, 21)


def test_two_years_vegetation():
    p = P.plan("How much vegetation did Tengah lose between 2019 and 2026?", TODAY)
    assert isinstance(p, Plan)
    assert p.args == {"place": "tengah", "index": "ndvi", "t0": "2019-01-01/2019-12-31",
                      "t1": "2025-11-21/2026-11-21"}


def test_since_year_coastline_uses_water_index():
    p = P.plan("How has the coastline at Tuas changed since 2018?", TODAY)
    assert p.args["index"] == "mndwi" and p.args["t0"].startswith("2018")


def test_multiword_place_and_built_up():
    p = P.plan("new construction on jurong island", TODAY)
    assert p.args["place"] == "jurong island" and p.args["index"] == "ndbi"


def test_open_question_goes_to_foundation_model():
    p = P.plan("What changed in Tengah since 2019?", TODAY)
    assert p.tool == "embedding_change" and p.args["model"] == "clay-v1.5"


def test_any_osm_place_and_drawn_box():
    p = P.plan("what changed in Sentosa?", TODAY)
    assert isinstance(p, Plan) and p.args["place"].lower() == "sentosa"
    p = P.plan("what is being built here?", TODAY, selection=(103.72, 1.35, 103.74, 1.37))
    assert p.tool == "embedding_change" and p.args["place"] is None and "bbox" in p.args


def test_unknown_place_and_oversized_area_ask():
    assert isinstance(P.plan("what changed in Atlantis?", TODAY), Clarify)
    big = P.plan("what changed in Paris?", TODAY)  # found, but too big for Clay: show it, ask to draw
    assert isinstance(big, Clarify) and big.bbox is not None and "Draw a smaller box" in big.message
    assert isinstance(P.plan("what changed in Singapore since 2019?", TODAY), Clarify)


def test_anywhere_on_earth_via_geocoder():
    p = P.plan("How much vegetation did Lisbon lose since 2019?", TODAY)
    assert isinstance(p, Plan) and p.args["place"] == "Lisbon" and p.args["index"] == "ndvi"
    assert p.args["bbox"] == [-9.16, 38.70, -9.12, 38.73]  # tools get the exact box
    pl = aoi.place_for("Lisbon", p.args["bbox"])
    assert pl.source == "named" and pl.name == "Lisbon"


def test_drawn_box_anywhere():
    p = P.plan("what is being built here?", TODAY, selection=(-46.70, -23.60, -46.68, -23.58))
    assert isinstance(p, Plan) and p.tool == "embedding_change"
    with pytest.raises(ValueError):
        aoi.from_bbox((0, 85, 1, 86))


def test_windows_clamp_and_order():
    assert windows(2010, None, TODAY)[0].startswith("2016")
    assert windows(2022, 2020, TODAY) == ("2022-01-01/2022-12-31", "2023-01-01/2023-12-31")
    assert windows(None, None, TODAY)[0].startswith("2021")


def test_place_resolution_curated_osm_fuzzy_and_drawn():
    assert aoi.resolve("Tengah").source == "curated"
    assert aoi.resolve("sentosa").source == "osm"
    assert aoi.resolve("Tengha").name == "tengah"  # typo
    p = aoi.place_for(None, (103.8, 1.3, 103.82, 1.32))
    assert p.source == "drawn" and not p.approximate
    with pytest.raises(ValueError):
        aoi.check_size(aoi.resolve("singapore"), "embedding_change")
    with pytest.raises(KeyError):
        aoi.resolve("Atlantis")
