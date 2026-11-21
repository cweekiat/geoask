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

from .. import aoi, mgrs
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
    "What changed at the Tesla Gigafactory Berlin since 2019?",
    "How busy is the Bay of Gibraltar with ships since August 2026?",
    "How steep is the terrain around Zermatt?",
    "What is being built in the area I drew?",
]

CAPABILITIES = (
    "I can measure how any area on Earth has changed between two years from Sentinel-2 "
    "satellite imagery: vegetation, water and coastline, built-up land, or change of any kind "
    "using the Clay foundation model. I can also describe terrain (elevation and slope) and work "
    "out what can be seen from a point, from the Copernicus 30 m elevation model, and count vessels "
    "pass by pass on Sentinel-1 radar (pattern of life at sea), and show a "
    "sharpened 2.5 m view of an area (super-resolution, for viewing only). Name a place, "
    "give coordinates (lat/lon, UTM or MGRS) or draw a box on the map."
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


def window_label(win: str, today: date | None = None) -> str:
    """'2019-01-01/2019-12-31' → '2019'; the trailing 12 months → 'the last 12 months'."""
    a, b = win.split("/")
    if a[5:] == "01-01" and b[5:] == "12-31" and a[:4] == b[:4]:
        return a[:4]
    try:
        d0, d1 = date.fromisoformat(a), date.fromisoformat(b)
    except ValueError:
        return win
    if 360 <= (d1 - d0).days <= 370 and d1 >= (today or date.today()) - timedelta(days=2):
        return "the last 12 months"
    return f"{a} to {b}"


def make_plan(tool: str, place: aoi.Place, t0: str, t1: str, planner: str,
              index: str | None = None) -> Plan | Clarify:
    try:
        aoi.check_size(place, tool)
    except ValueError as e:  # too big: show the place so the user can draw part of it
        return Clarify(str(e), bbox=place.bbox)
    where = _label(place)
    args = {"place": None if place.source == "drawn" else place.name, "t0": t0, "t1": t1}
    if place.source != "curated":  # tools get the exact box; names are only labels
        args["bbox"] = list(place.bbox)
    if tool == "embedding_change":
        args["model"] = "clay-v1.5"
        why = f"Any change over {where}, using the Clay foundation model"
    else:
        args["index"] = index
        why = f"{TOPIC_LABEL[index][0].upper() + TOPIC_LABEL[index][1:]} change over {where}"
    return Plan(tool, args, f"{why}: {window_label(t0)} vs {window_label(t1)}.", planner)


_AFTER_PREP = re.compile(
    r"\b(?:in|at|around|near|of|over|for)\s+(?:the\s+)?"
    r"([A-Z][\w'.-]*(?:[ ,]+(?:[A-Z][\w'.-]*|de|da|do|del|di|la|le|of|on|upon|am|an))*)")


_COORD_PATTERNS = [
    re.compile(r"-?\d{1,2}\.\d+\s*,\s*-?\d{1,3}\.\d+"),  # lat, lon
    re.compile(r"\b\d{1,2}\s?[C-HJ-NP-X]\s?[A-HJ-NP-Z][A-HJ-NP-V](?:\s?\d{1,5}\s?\d{1,5})?\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}\s?[NS]\s+\d{5,7}(?:\.\d+)?\s*m?E?\s+\d{6,8}(?:\.\d+)?\s*m?N?\b", re.IGNORECASE),
]


def find_point_in_text(q: str) -> tuple[float, float] | None:
    """A coordinate written in the question (lat/lon, MGRS or UTM) → (lon, lat)."""
    for pat in _COORD_PATTERNS:
        for m in pat.finditer(q):
            if (pt := mgrs.parse_coordinates(m.group(0))) is not None:
                return pt
    return None


def point_plan(tool: str, question: str, planner: str, place: aoi.Place | None,
               radius_km: float | None = None, height_m: float | None = None) -> Plan | Clarify:
    """Viewshed: the observer is a coordinate in the question, else the centre of the place."""
    pt = find_point_in_text(question)
    if pt is None and place is not None:
        w, s, e, n = place.bbox
        pt = ((w + e) / 2, (s + n) / 2)
    if pt is None:
        return Clarify("Where should the observer stand? Give coordinates (lat/lon, UTM or MGRS), "
                       "a place, or draw a box and I'll use its centre.", EXAMPLES)
    said = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", question)}
    if radius_km is None and (m := re.search(r"(\d+(?:\.\d+)?)\s*(km|kilomet)", question, re.IGNORECASE)):
        radius_km = float(m.group(1))
    if height_m is None and (m := re.search(r"(\d+(?:\.\d+)?)\s*m(?:etres?|eters?)?\s+"
                                            r"(?:mast|tower|high|tall|observer|above)", question, re.IGNORECASE)):
        height_m = float(m.group(1))
    radius_km = radius_km if radius_km in said else 5.0  # only numbers the user actually wrote
    height_m = height_m if height_m in said else 2.0
    args = {"lon": round(pt[0], 6), "lat": round(pt[1], 6), "radius_m": radius_km * 1000,
            "observer_h": height_m, "target_h": 2.0}
    return Plan(tool, args, f"What a {height_m:g} m observer at {mgrs.to_mgrs(*pt, 4)} can see "
                f"within {radius_km:g} km (Copernicus 30 m).", planner)


def terrain_plan(place: aoi.Place, planner: str) -> Plan | Clarify:
    try:
        aoi.check_size(place, "terrain")
    except ValueError as e:
        return Clarify(str(e), bbox=place.bbox)
    where = _label(place)
    args = {"place": None if place.source == "drawn" else place.name, "bbox": list(place.bbox)}
    return Plan("terrain", args, f"Elevation and slope over {where} (Copernicus 30 m).", planner)


_SHARPEN = re.compile(r"\b(sharpen|sharper|super[- ]?res\w*|enhance|upscal\w*|higher[- ]res\w*|"
                      r"high[- ]res\w*|2\.5 ?m|clearer image|more detail)\b", re.IGNORECASE)


def sharpen_plan(place: aoi.Place, question: str, today: date, planner: str) -> Plan | Clarify:
    try:
        aoi.check_size(place, "super_resolve")
    except ValueError as e:
        return Clarify(str(e), bbox=place.bbox)
    years = sorted({int(y) for y in re.findall(r"\b(20[12]\d)\b", question)})
    _, win = windows(None, None, today) if not years else windows(years[-1] - 1, years[-1], today)
    args = {"place": None if place.source == "drawn" else place.name, "bbox": list(place.bbox),
            "window": win, "model": "sen2sr-lite"}
    return Plan("super_resolve", args, f"Sharpen the clearest image of {_label(place)} from "
                f"{window_label(win)} to 2.5 m (for viewing only).", planner)


_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH_YEAR = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(20[12]\d)\b",
                         re.IGNORECASE)
_ACTIVITY = re.compile(r"\b(ships?|vessels?|boats?|tankers?|maritime|shipping|anchorage|"
                       r"port activity|traffic at sea|pattern[- ]of[- ]life|how busy|busier|"
                       r"activity)\b", re.IGNORECASE)


def activity_plan(place: aoi.Place, question: str, today: date, planner: str) -> Plan | Clarify:
    try:
        aoi.check_size(place, "activity")
    except ValueError as e:
        return Clarify(str(e), bbox=place.bbox)
    years = sorted({int(y) for y in re.findall(r"\b(20[12]\d)\b", question)})
    since = _MONTH_YEAR.search(question)
    if since:  # "since August 2026" → from the 1st of that month to today
        m = _MONTHS.index(since.group(1)[:3].lower()) + 1
        win = f"{int(since.group(2))}-{m:02d}-01/{today.isoformat()}"
    elif years and years[0] < today.year:
        win = f"{years[0]}-01-01/{min(years[-1], today.year - 1)}-12-31"
    else:
        win = windows(None, None, today)[1]
    args = {"place": None if place.source == "drawn" else place.name, "bbox": list(place.bbox),
            "window": win}
    return Plan("activity", args, f"Count vessels on every radar pass over {_label(place)}, "
                f"{window_label(win, today)}, and flag unusual days.", planner)


_TERRAIN = re.compile(r"\b(elevation|terrain|slope|steep|altitude|how high|hill|mountain|"
                      r"relief|contour|height above sea)\b", re.IGNORECASE)
_VISIBILITY = re.compile(r"\b(viewshed|line of sight|visible from|can\b[^?]{0,60}\bsee|seen from|"
                         r"observation post|overlook|vantage)\b", re.IGNORECASE)


def _label(place: aoi.Place) -> str:
    if place.source == "drawn":
        return "the area you drew"
    return place.name if any(c.isupper() or c.isdigit() for c in place.name) else place.name.title()


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
    cands.sort(key=len, reverse=True)  # "Bay of Gibraltar" before "Gibraltar"
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


_CAPS = re.compile(r"\b[A-Z][\w'.-]*(?: (?:(?:of|de|del|da|do|di|la|le|the|am|an) )?[A-Z][\w'.-]*)*")
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
            pt = None if selection else find_point_in_text(question)
            place = (aoi.from_bbox(selection) if selection else
                     None if pt else find_place_in_text(question))
        except ValueError as e:
            return Clarify(str(e))
        if _VISIBILITY.search(q):
            return point_plan("viewshed", question, self.name, place)
        if place is None and (pt := find_point_in_text(question)):
            place = aoi.from_bbox((pt[0] - 0.01, pt[1] - 0.01, pt[0] + 0.01, pt[1] + 0.01),
                                  mgrs.to_mgrs(*pt, 4), "named")
        if place is None:
            return Clarify(f"{CAPABILITIES} Which area should I look at?", EXAMPLES)
        if _TERRAIN.search(q):
            return terrain_plan(place, self.name)
        if _ACTIVITY.search(q):
            return activity_plan(place, question, today, self.name)
        if _SHARPEN.search(q):
            return sharpen_plan(place, question, today, self.name)
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
        "name": "describe_terrain",
        "description": "Elevation, height, slope, hills or relief of an area (not change over "
                       "time).",
        "parameters": {"type": "object", "properties": {
            "place": {"type": "string", "description": "Place name; empty if the user drew a "
                      "box or gave coordinates."}}}}},
    {"type": "function", "function": {
        "name": "visibility_from",
        "description": "What can be seen from a point: viewshed, line of sight, observation "
                       "or vantage points.",
        "parameters": {"type": "object", "properties": {
            "place": {"type": "string", "description": "Place to stand at; empty if the user "
                      "gave coordinates or drew a box."},
            "radius_km": {"type": "number", "description": "How far to look; only if the user "
                          "said"},
            "observer_height_m": {"type": "number", "description": "Eye or mast height in "
                                  "metres; only if the user said"}}}}},
    {"type": "function", "function": {
        "name": "count_activity",
        "description": "Pattern of life at sea: how many ships or vessels are in an area on each "
                       "satellite radar pass, how busy it is, and which days were unusual.",
        "parameters": {"type": "object", "properties": {
            "place": {"type": "string", "description": "Port, strait, anchorage or sea area; "
                      "empty if the user drew a box."}}}}},
    {"type": "function", "function": {
        "name": "sharpen_image",
        "description": "Show a sharper, higher-resolution (super-resolved, 2.5 m) image of an "
                       "area, for viewing. Not for measuring change.",
        "parameters": {"type": "object", "properties": {
            "place": {"type": "string", "description": "Place name; empty if the user drew a box."},
            "year": {"type": "integer", "description": "Only if the user named a year"}}}}},
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
        if fn["name"] == "measure_change" and _VISIBILITY.search(question):
            fn, args = {"name": "visibility_from"}, {}  # deterministic override, like _OPEN
        if fn["name"] == "measure_change" and _SHARPEN.search(question) and not _OPEN.search(question):
            fn = {"name": "sharpen_image"}
        if fn["name"] == "measure_change" and _ACTIVITY.search(question) and not _OPEN.search(question):
            fn = {"name": "count_activity"}
        if fn["name"] == "count_activity":
            try:
                place = (aoi.from_bbox(selection) if selection else
                         aoi.resolve(str(args["place"])) if args.get("place") else
                         find_place_in_text(question))
            except (KeyError, ValueError) as e:
                return Clarify(str(e).strip("'\""), EXAMPLES)
            if place is None:
                return Clarify(f"{CAPABILITIES} Which area should I look at?", EXAMPLES)
            return activity_plan(place, question, today, self.name)
        if fn["name"] == "sharpen_image":
            try:
                place = (aoi.from_bbox(selection) if selection else
                         aoi.resolve(str(args["place"])) if args.get("place") else
                         find_place_in_text(question))
            except (KeyError, ValueError) as e:
                return Clarify(str(e).strip("'\""), EXAMPLES)
            if place is None:
                return Clarify(f"{CAPABILITIES} Which area should I look at?", EXAMPLES)
            return sharpen_plan(place, question, today, self.name)
        if fn["name"] in ("describe_terrain", "visibility_from"):
            try:
                place = (aoi.from_bbox(selection) if selection else
                         aoi.resolve(str(args["place"])) if args.get("place") else
                         find_place_in_text(question))
            except (KeyError, ValueError) as e:
                if fn["name"] == "describe_terrain" or not find_point_in_text(question):
                    return Clarify(str(e).strip("'\""), EXAMPLES)
                place = None
            if fn["name"] == "visibility_from":
                return point_plan("viewshed", question, self.name, place,
                                  _num(args.get("radius_km")), _num(args.get("observer_height_m")))
            if place is None and (pt := find_point_in_text(question)):
                place = aoi.from_bbox((pt[0] - 0.01, pt[1] - 0.01, pt[0] + 0.01, pt[1] + 0.01),
                                      mgrs.to_mgrs(*pt, 4), "named")
            if place is None:
                return Clarify(f"{CAPABILITIES} Which area should I look at?", EXAMPLES)
            return terrain_plan(place, self.name)
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


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def default_planner() -> Planner:
    """Ollama if its model is installed and running, else rule-based."""
    return LLMPlanner() if llm.available() else RuleBasedPlanner()
