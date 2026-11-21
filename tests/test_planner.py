from datetime import date

from geoask.agent.planner import Clarify, Plan, RuleBasedPlanner

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


def test_unknown_place_asks():
    assert isinstance(P.plan("what changed in Paris?", TODAY), Clarify)


def test_open_question_goes_to_foundation_model():
    p = P.plan("What changed in Tengah since 2019?", TODAY)
    assert p.tool == "embedding_change" and p.args["model"] == "clay-v1.5"
