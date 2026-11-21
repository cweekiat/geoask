"""Turn a question into a tool call.

Two planners share one output contract and the same validation:

* ``LLMPlanner``: a local Ollama model (default Qwen 2.5 7B) reads any free-form question and picks
  a tool with *simple* arguments: topic, place, years. Python turns those into exact date windows
  and checks them; the model never sets dates, thresholds or numbers.
* ``RuleBasedPlanner``: keyword rules. Needs no model; it's also the fallback whenever the LLM
  is unavailable or returns something invalid.

A drawn box (``selection``) always wins over a place name.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from .. import aoi
from . import llm


@dataclass
class Plan:
    tool: str
    args: dict
    explanation: str
    planner: str


@dataclass
class Clarify:
    message: str
    suggestions: list[str] = field(default_factory=list)
    bbox: aoi.BBox | None = None  # a place we found but can't analyse as is: the map flies there


@dataclass
class Reply:
    """A direct answer that needs no imagery (e.g. "what can you do?"). Never contains numbers
    about places: those only come from tools."""

    message: str
    planner: str


Outcome = Plan | Clarify | Reply


class Planner(Protocol):
    name: str

    def plan(self, question: str, today: date | None = None,
             selection: aoi.BBox | None = None) -> Outcome: ...


TOPICS = {"vegetation": "ndvi", "water": "mndwi", "built-up": "ndbi"}
TOPIC_LABEL = {"ndvi": "vegetation (NDVI)", "mndwi": "water (MNDWI)",
               "ndbi": "built-up land (NDBI)"}
_INDEX_WORDS = [
    ("ndbi", ("built-up", "built up", "construction", "urban", "buildings", "bare", "cleared land")),
    ("mndwi", ("water", "flood", "reservoir", "coast", "reclam", "shoreline", "sea", "pond")),
    ("ndvi", ("vegetation", "forest", "green", "tree", "park", "jungle", "mangrove", "plant")),
]

EXAMPLES = [
    "What changed in Tengah since 2019?",
    "How much vegetation did Tengah lose between 2019 and 2026?",
    "How has the coastline at Tuas changed since 2018?",
    "What is being built in the area I drew?",
]

CAPABILITIES = (
    "I can measure how any area on Earth has changed between two years from Sentinel-2 "
    "satellite imagery: vegetation, water and coastline, built-up land, or change of any kind "
    "using the Clay foundation model. Name a place or draw a box on the map, and give the years."
)


# ---- shared helpers ------------------------------------------------------------------------

def windows(start_year: int | None, end_year: int | None, today: date) -> tuple[str, str]:
    """Year(s) → (t0, t1) date windows. The latest window is the last 12 months, so the
    current year never means a half-empty search."""
    last12 = f"{(today - timedelta(days=365)).isoformat()}/{today.isoformat()}"
    lo = 2016
    if end_year is not None:
        end_year = min(max(end_year, lo + 1), today.year)
    if start_year is None:
        start_year = (end_year or today.year) - 5
    start_year = min(max(start_year, lo), today.year - 1)
    t0 = f"{start_year}-01-01/{start_year}-12-31"
    if end_year is None or end_year >= today.year:
        return t0, last12
    if end_year <= start_year:
        end_year = start_year + 1
    return t0, f"{end_year}-01-01/{end_year}-12-31"


def make_plan(tool: str, place: aoi.Place, t0: str, t1: str, planner: str,
              index: str | None = None) -> Plan | Clarify:
    try:
        aoi.check_size(place, tool)
    except ValueError as e:  # too big: show the place so the user can draw part of it
        return Clarify(str(e), bbox=place.bbox)
    where = "the area you drew" if place.source == "drawn" else place.name.title()
    args = {"place": None if place.source == "drawn" else place.name, "t0": t0, "t1": t1}
    if place.source != "curated":  # tools get the exact box; names are only labels
        args["bbox"] = list(place.bbox)
    if tool == "embedding_change":
        args["model"] = "clay-v1.5"
        why = f"Look for any kind of change over {where} with the Clay foundation model"
    else:
        args["index"] = index
        why = f"Compare {TOPIC_LABEL[index]} over {where}"
    return Plan(tool, args, f"{why}: clearest date in {t0} vs clearest date in {t1}.", planner)


_AFTER_PREP = re.compile(
    r"\b(?:in|at|around|near|of|over|for)\s+(?:the\s+)?"
    r"([A-Z][\w'.-]*(?:[ ,]+(?:[A-Z][\w'.-]*|de|da|do|del|di|la|le|of|on|upon|am|an))*)")


def find_place_in_text(q: str) -> aoi.Place | None:
    """The place a question is about: the longest bundled name it contains, else a capitalised
    name after "in / at / around…" looked up with the geocoder."""
    ql = f" {q.lower()} "
    names = [k for k in aoi.PLACES if k != "singapore"] + list(aoi.gazetteer())
    hits = [n for n in names if f" {n} " in ql or f" {n}?" in ql or f" {n}," in ql
            or f" {n}." in ql or f" {n}'" in ql]
    if hits:
        return aoi.resolve(max(hits, key=len))
    # Names after a preposition first, then any other capitalised run past the first word.
    cands = [m.group(1) for m in _AFTER_PREP.finditer(q)]
    cands += [m.group(0) for m in _CAPS.finditer(q) if m.start() > 0]
    seen: set[str] = set()
    for name in (c.strip(" ,.") for c in cands):
        if not name or name.lower() in seen or name.lower() in _NOT_PLACES:
            continue
        seen.add(name.lower())
        try:
            return aoi.resolve(name)
        except KeyError:
            continue
    return None


_CAPS = re.compile(r"\b[A-Z][\w'.-]*(?: [A-Z][\w'.-]*)*")
_NOT_PLACES = {"i", "ndvi", "ndwi", "mndwi", "ndbi", "clay", "sentinel", "what", "how", "has",
               "did", "is", "are", "was", "the area", "this area", "here"}


# ---- rule-based ----------------------------------------------------------------------------

class RuleBasedPlanner:
    name = "rule-based"

    def plan(self, question: str, today: date | None = None,
             selection: aoi.BBox | None = None) -> Outcome:
        q = question.lower()
        today = today or date.today()
        try:
            place = aoi.from_bbox(selection) if selection else find_place_in_text(question)
        except ValueError as e:
            return Clarify(str(e))
        if place is None:
            return Clarify(f"{CAPABILITIES} Which area should I look at?", EXAMPLES)
        index = next((i for i, words in _INDEX_WORDS if any(w in q for w in words)), None)
        years = sorted({int(y) for y in re.findall(r"\b(20[12]\d)\b", q)})
        t0, t1 = windows(years[0] if years else None,
                         years[-1] if len(years) > 1 else None, today)
        tool = "index_change" if index else "embedding_change"
        return make_plan(tool, place, t0, t1, self.name, index)


# ---- LLM (Ollama) --------------------------------------------------------------------------

_TOOLS = [
    {"type": "function", "function": {
        "name": "measure_change",
        "description": "Measure how an area changed between two years. Pick the topic from "
                       "WHAT the user asks about, never from the kind of place: "
                       "'vegetation' = trees, forest, greenery; 'water' = water extent, "
                       "coastline, land reclamation, flooding; 'built-up' = how much land is "
                       "now built on / urban growth; 'any' = open questions like 'what "
                       "changed', 'what is happening', 'what is being built here', "
                       "'anything unusual' (even at a reservoir, park or airport).",
        "parameters": {"type": "object", "required": ["topic"], "properties": {
            "topic": {"type": "string", "enum": ["vegetation", "water", "built-up", "any"]},
            "place": {"type": "string", "description": "Place name exactly as the user wrote "
                      "it, anywhere in the world, with its city or country if the user gave "
                      "one. Leave empty if the user drew a box."},
            "start_year": {"type": "integer", "description": "Earlier year, e.g. 2019"},
            "end_year": {"type": "integer", "description": "Later year; omit for 'now'"},
        }}}},
    {"type": "function", "function": {
        "name": "cannot_answer_from_imagery",
        "description": "Use when the question isn't about how a place looks or changed "
                       "(e.g. prices, population, opinions), or no place can be determined.",
        "parameters": {"type": "object", "required": ["reason"], "properties": {
            "reason": {"type": "string"}}}}},
]


class LLMPlanner:
    def __init__(self, model: str = llm.MODEL) -> None:
        self.model = model
        self.name = f"ollama:{model}"
        self.fallback = RuleBasedPlanner()

    def plan(self, question: str, today: date | None = None,
             selection: aoi.BBox | None = None) -> Outcome:
        today = today or date.today()
        system = (
            "You are the planner for GeoAsk, which answers questions about any place on Earth "
            "by measuring Sentinel-2 satellite imagery. Always call exactly one tool. "
            f"Today is {today.isoformat()}. Imagery exists from 2016 onwards. "
            + ("The user has drawn a box on the map: that box is the area to analyse, "
               "so leave place empty. " if selection else
               "The user has not drawn a box, so the place must come from the question. ")
            + "Never answer with numbers yourself.")
        try:
            msg = llm.chat([{"role": "system", "content": system},
                            {"role": "user", "content": question}], tools=_TOOLS,
                           model=self.model, timeout=60)
        except llm.LLMUnavailable:
            return self._fallback(question, today, selection, "LLM unavailable")
        calls = msg.get("tool_calls") or []
        if not calls:
            return self._fallback(question, today, selection, "no tool chosen")
        fn = calls[0]["function"]
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return self._fallback(question, today, selection, "unreadable arguments")
        if fn["name"] == "cannot_answer_from_imagery":
            return Reply(f"{CAPABILITIES}", self.name)
        topic = str(args.get("topic", "any")).lower()
        if _OPEN.search(question):  # deterministic override: open questions → any change
            topic = "any"
        index = TOPICS.get(topic)
        try:
            if selection:
                place = aoi.from_bbox(selection)
            elif args.get("place"):
                place = aoi.resolve(str(args["place"]))
            else:
                place = find_place_in_text(question)
            if place is None:
                return Clarify(f"{CAPABILITIES} Which area should I look at?", EXAMPLES)
            # Years only count if the user gave them (or a relative period the model resolved).
            said = {int(y) for y in re.findall(r"\b(20[12]\d)\b", question)}
            relative = bool(_RELATIVE.search(question))
            sy, ey = _int(args.get("start_year")), _int(args.get("end_year"))
            sy = sy if (sy in said or relative) else (min(said) if said else None)
            ey = ey if (ey in said or relative) else (max(said) if len(said) > 1 else None)
            t0, t1 = windows(sy, ey, today)
            return make_plan("index_change" if index else "embedding_change", place, t0, t1,
                             self.name, index)
        except (KeyError, ValueError) as e:
            return Clarify(str(e).strip("'\""), EXAMPLES)

    def _fallback(self, q, today, selection, why) -> Outcome:
        out = self.fallback.plan(q, today, selection)
        if isinstance(out, Plan):
            out.planner = f"rule-based (fallback: {why})"
        return out


_OPEN = re.compile(r"what(?:'s| is| has)? (?:been |being )?(?:built|chang|happen)|"
                   r"anything (?:new|unusual|different)|unusual|what changed", re.IGNORECASE)
_RELATIVE = re.compile(r"\b(last|past|recent|ago|since|over the)\b", re.IGNORECASE)


def _int(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def default_planner() -> Planner:
    """Ollama if its model is installed and running, else rule-based."""
    return LLMPlanner() if llm.available() else RuleBasedPlanner()
