from geoask.agent.answer import facts, numbers_ok, template_answer

R = {"tool": "index_change", "place": "tengah", "place_source": "curated", "date0": "2019-01-01",
     "date1": "2026-03-25", "compared_fraction": 1.0, "label": "vegetation", "index": "ndvi",
     "loss_ha": 229.96, "gain_ha": 34.12, "mean0": 0.551, "mean1": 0.432}


def test_numbers_from_facts_pass():
    ok, bad = numbers_ok("Tengah lost about 230 ha of vegetation between 2019 and 2026 "
                         "(mean NDVI 0.55 to 0.43), with 100% clear.", facts(R))
    assert ok, bad


def test_invented_numbers_are_caught():
    ok, bad = numbers_ok("Tengah lost 230 ha, roughly 15 football fields, about 40%.", facts(R))
    assert not ok and set(bad) == {"15", "40"}


def test_template_passes_its_own_check():
    assert numbers_ok(template_answer(R), facts(R))[0]
    e = {"tool": "embedding_change", "place": "x", "place_source": "drawn", "date0": "2020-01-02",
         "date1": "2025-12-05", "compared_fraction": .97, "changed_ha": 120.4, "area_ha": 980.0,
         "patch_m": 80.0}
    assert numbers_ok(template_answer(e), facts(e))[0]
    assert "the area you drew" in template_answer(e)
