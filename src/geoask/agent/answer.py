"""Write the final answer, without letting the language model invent numbers.

1. ``facts(result)`` turns a tool result into a short list of measured facts, numbers pre-formatted.
2. The LLM writes 2–3 sentences from those facts only.
3. ``numbers_ok`` checks every number in the text appears in the facts, the dates or the question.
   If any doesn't, the deterministic ``template_answer`` is used instead, and the UI says so.
"""

from __future__ import annotations

import re

from . import llm

_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _place(r: dict) -> str:
    if r.get("place_source") == "drawn":
        return "the area you drew"
    return r["place"] if any(c.isupper() for c in r["place"]) else r["place"].title()


def facts(r: dict) -> list[str]:
    if r["tool"] == "terrain":
        return [f"Area: {_place(r)}", ("Source: Copernicus 30 m elevation model (a surface model: "
                "it includes buildings and tree canopy)"),
                f"Lowest elevation: {r['elev_min_m']:.0f} m", f"Highest elevation: {r['elev_max_m']:.0f} m",
                f"Mean elevation: {r['elev_mean_m']:.0f} m", f"Relief (highest minus lowest): {r['relief_m']:.0f} m",
                f"Mean slope: {r['slope_mean_deg']:.0f} degrees",
                f"Area steeper than 15 degrees: {r['steep_ha']:.0f} ha",
                f"Area steeper than 30 degrees: {r['very_steep_ha']:.0f} ha",
                f"Analysed area: {r['area_ha']:.0f} ha"]
    if r["tool"] == "activity":
        out = [f"Area: {_place(r)}", "Sensor: Sentinel-1 radar (sees through cloud, day and night)",
               f"Radar passes analysed: {r['passes']}, from {r['date0']} to {r['date1']}",
               f"Vessels per pass: typically {r['median_count']:.0f}, average {r['mean_count']:.0f}",
               f"Busiest pass: {r['max_date']} with {r['max_count']} vessels",
               "Only vessels longer than about 20-30 m are reliably seen; their identity is unknown",
               (f"Persistent targets set aside (same spot on almost every pass): "
               f"{r.get('persistent_targets', 0)}")]
        for u in r["unusual"]:
            out.append(f"Unusually {u['kind']} pass: {u['date']} with {u['count']} vessels")
        if not r["unusual"]:
            out.append("No pass was unusually busy or quiet")
        return out
    if r["tool"] == "super_resolve":
        return [f"Area: {_place(r)}", f"Image date: {r['date']}",
                f"Sharpened from {r['grid']['res_m']:g} m to {r['out_res_m']:g} m with {r['model']}",
                "For viewing only: the added detail is a model's estimate and is never measured",
                ("Mean difference from the real 10 m pixels after averaging back: "
                f"{r['consistency_mean']:.3f} reflectance")]
    if r["tool"] == "viewshed":
        pct = 100 * r["visible_ha"] / r["area_ha"] if r["area_ha"] else 0
        return [("Source: Copernicus 30 m elevation model (it includes buildings and trees, which "
                "block views)"), f"Observer height above the surface: {r['observer_h_m']:g} m",
                f"Target height: {r['target_h_m']:g} m", f"Radius: {r['radius_m'] / 1000:g} km",
                f"Surface elevation at the observer: {r['observer_elev_m']:.0f} m",
                f"Visible area: {r['visible_ha']:.0f} ha",
                f"Share of the circle that is visible: {pct:.0f}%"]
    where = _place(r)
    pct = 100 * r.get("compared_fraction", 0)
    out = [f"Area: {where}", f"Before date: {r['date0']}", f"After date: {r['date1']}",
           f"Share of the area clear of cloud on both dates: {pct:.0f}%"]
    if r["tool"] == "embedding_change":
        share = 100 * r["changed_ha"] / r["area_ha"] if r.get("area_ha") else 0
        out += [f"Method: the Clay foundation model compared every {r['patch_m']:.0f} m patch",
                f"Area that changed (any kind of change): {r['changed_ha']:.0f} ha",
                f"Share of the analysed area that changed: {share:.0f}%",
                f"Analysed area: {r['area_ha']:.0f} ha"]
    else:
        out += [f"Measured: {r['label']} ({r['index'].upper()})",
                f"{r['label'].capitalize()} lost: {r['loss_ha']:.0f} ha",
                f"{r['label'].capitalize()} gained: {r['gain_ha']:.0f} ha",
                f"Mean {r['index'].upper()} before: {r['mean0']:.2f}; after: {r['mean1']:.2f}"]
    return out


def template_answer(r: dict) -> str:
    if r["tool"] == "terrain":
        return (f"{_place(r)} ranges from {r['elev_min_m']:.0f} m to {r['elev_max_m']:.0f} m "
                f"(mean {r['elev_mean_m']:.0f} m). Mean slope is {r['slope_mean_deg']:.0f}°, and "
                f"{r['steep_ha']:.0f} ha is steeper than 15°. Heights include buildings and trees.")
    if r["tool"] == "activity":
        unusual = "; ".join(f"{u['date']} was unusually {u['kind']} ({u['count']})"
                            for u in r["unusual"]) or "no pass stood out"
        return (f"Over {r['passes']} Sentinel-1 radar passes from {r['date0']} to {r['date1']}, "
                f"{_place(r)} typically had {r['median_count']:.0f} vessels in view (busiest: "
                f"{r['max_count']} on {r['max_date']}). Unusual days: {unusual}. Small craft are "
                "missed, and radar can't tell who the vessels are.")
    if r["tool"] == "super_resolve":
        return (f"Here is {_place(r)} on {r['date']}, sharpened from {r['grid']['res_m']:g} m to "
                f"{r['out_res_m']:g} m with {r['model']}. It's for viewing only: the extra detail "
                "is the model's estimate, consistent with the real pixels but not measured.")
    if r["tool"] == "viewshed":
        pct = 100 * r["visible_ha"] / r["area_ha"] if r["area_ha"] else 0
        return (f"A {r['observer_h_m']:g} m observer here can see about {r['visible_ha']:.0f} ha "
                f"({pct:.0f}%) of the ground within {r['radius_m'] / 1000:g} km. Buildings and "
                "trees in the 30 m elevation model block views; small obstacles are missed.")
    where = _place(r)
    if r["tool"] == "embedding_change":
        share = 100 * r["changed_ha"] / r["area_ha"] if r.get("area_ha") else 0
        return (f"Between {r['date0']} and {r['date1']}, about {r['changed_ha']:.0f} ha of "
                f"{where} ({share:.0f}% of the analysed area) changed, according to the Clay "
                f"foundation model. The highlighted patches on the map show where.")
    return (f"Between {r['date0']} and {r['date1']}, {where} lost about {r['loss_ha']:.0f} ha "
            f"and gained about {r['gain_ha']:.0f} ha of {r['label']}. Mean "
            f"{r['index'].upper()} went from {r['mean0']:.2f} to {r['mean1']:.2f}.")


def _norm(tok: str) -> str:
    t = tok.replace(",", "").lstrip("-")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t


def numbers_ok(text: str, allowed_sources: list[str]) -> tuple[bool, list[str]]:
    allowed = {_norm(m) for src in allowed_sources for m in _NUM.findall(src)}
    for src in allowed_sources:  # dates like 2019-01-01 also allow 2019, 01, 1
        for d in re.findall(r"\d{4}-\d{2}-\d{2}", src):
            y, m, day = d.split("-")
            allowed |= {y, m, day, str(int(m)), str(int(day))}
    bad = [m for m in _NUM.findall(text) if _norm(m) not in allowed]
    return (not bad, bad)


def write(question: str, r: dict, model: str = llm.MODEL) -> tuple[str, str]:
    """Return (answer text, source), where source is the model name or 'template'."""
    fs = facts(r)
    prompt = ("Answer the user's question in 2-3 plain sentences using ONLY these measured "
              "facts. Use the numbers exactly as written; don't compute new numbers or add "
              "any others. Don't speculate about causes. Speak directly to the user as GeoAsk; "
              "never mention 'facts' or 'the data provided'.\n\n"
              "Facts:\n- " + "\n- ".join(fs) + f"\n\nQuestion: {question}")
    try:
        msg = llm.chat([{"role": "user", "content": prompt}], model=model, timeout=60)
        text = (msg.get("content") or "").strip()
    except llm.LLMUnavailable:
        return template_answer(r), "template"
    ok, _bad = numbers_ok(text, fs + [question])
    if not text or not ok:
        return template_answer(r), "template (the model's wording failed the number check)"
    return text, model
