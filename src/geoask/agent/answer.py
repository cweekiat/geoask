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
    return "the area you drew" if r.get("place_source") == "drawn" else r["place"].title()


def facts(r: dict) -> list[str]:
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
