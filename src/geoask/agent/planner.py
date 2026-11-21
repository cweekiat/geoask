"""Turn a question into a tool call.

``Planner`` is the interface every provider implements: Apple Foundation Models (in the app),
an OpenAI-compatible local endpoint such as llama.cpp or Ollama (planned), or this rule-based
planner, which needs no language model and is always available as the fallback.

Planners only choose tools and arguments. They never produce numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from .. import aoi


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


class Planner(Protocol):
    name: str

    def plan(self, question: str, today: date | None = None) -> Plan | Clarify: ...


_INDEX_WORDS = [
    ("ndbi", ("built", "construction", "urban", "development", "building", "bare", "cleared land")),
    ("mndwi", ("water", "flood", "reservoir", "coast", "reclam", "shoreline", "sea", "pond")),
    ("ndvi", ("vegetation", "forest", "green", "tree", "park", "jungle", "mangrove", "plant")),
]

EXAMPLES = [
    "What changed in Tengah since 2019?",
    "How much vegetation did Tengah lose between 2019 and 2026?",
    "How has the coastline at Tuas changed since 2018?",
    "How much new built-up land is there in Punggol since 2019?",
]


class RuleBasedPlanner:
    name = "rule-based"

    def plan(self, question: str, today: date | None = None) -> Plan | Clarify:
        q = question.lower()
        today = today or date.today()
        place = next((p for p in sorted(aoi.PLACES, key=len, reverse=True)
                      if p != "singapore" and p in q), None)
        if place is None:
            known = ", ".join(p.title() for p in aoi.PLACES if p != "singapore")
            return Clarify(f"Which area should I look at? I can currently analyse: {known}.",
                           EXAMPLES)
        index = next((i for i, words in _INDEX_WORDS if any(w in q for w in words)), None)
        years = sorted({int(y) for y in re.findall(r"\b(20[12]\d)\b", q)
                        if 2016 <= int(y) <= today.year})
        last12 = f"{(today - timedelta(days=365)).isoformat()}/{today.isoformat()}"
        if len(years) >= 2:
            y0, y1 = years[0], years[-1]
            t0 = f"{y0}-01-01/{y0}-12-31"
            t1 = last12 if y1 == today.year else f"{y1}-01-01/{y1}-12-31"
        elif len(years) == 1:
            t0, t1 = f"{years[0]}-01-01/{years[0]}-12-31", last12
        else:
            y0 = today.year - 5
            t0, t1 = f"{y0}-01-01/{y0}-12-31", last12
        if index is None:  # no topic named: look for change of any kind with a foundation model
            return Plan(
                tool="embedding_change",
                args={"place": place, "t0": t0, "t1": t1, "model": "clay-v1.5"},
                explanation=f"Look for any kind of change over {place.title()} with the Clay "
                            f"foundation model: clearest date in {t0} vs clearest date in {t1}.",
                planner=self.name,
            )
        why = {"ndvi": "vegetation (NDVI)", "mndwi": "water (MNDWI)",
               "ndbi": "built-up land (NDBI)"}[index]
        return Plan(
            tool="index_change",
            args={"place": place, "index": index, "t0": t0, "t1": t1},
            explanation=f"Compare {why} over {place.title()}: clearest date in {t0} vs "
                        f"clearest date in {t1}.",
            planner=self.name,
        )
