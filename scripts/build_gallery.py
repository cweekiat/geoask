"""Precompute one real result per tool for the Pages demo (web/gallery/<tool>/).

Each example question from the tool catalogue goes through the rule-based planner and the real
tool; the plan, progress steps, result and template answer are saved, so Demo mode replays exactly
what Live mode produced.

    python scripts/build_gallery.py                 # all tools that aren't in the gallery yet
    python scripts/build_gallery.py activity --force
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

from geoask.agent import answer
from geoask.agent.catalog import TOOLS
from geoask.agent.planner import Plan, RuleBasedPlanner
from geoask.server import _run

GALLERY = Path(__file__).resolve().parents[1] / "web" / "gallery"
TODAY = date(2026, 11, 21)


def build(tool: dict, force: bool) -> None:
    dest = GALLERY / tool["id"]
    if dest.exists() and not force:
        print(f"skip {tool['id']}")
        return
    plan = RuleBasedPlanner().plan(tool["example"], TODAY)
    assert isinstance(plan, Plan), plan
    steps: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        import geoask.server as srv

        srv.OUT = Path(tmp)
        result = None
        for kind, payload in _run(plan.tool, plan.args):
            if kind == "step":
                print(" ", payload)
                steps.append(payload)
            else:
                result = payload
        src = Path(tmp) / result["id"]
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("*.tif"))
    result["demo"] = {"question": tool["example"], "plan": asdict(plan) | {"planner": "rule-based (demo replay)"},
                      "steps": steps, "answer": answer.template_answer(result)}
    (dest / "result.json").write_text(json.dumps(result, indent=1, default=str))
    size = sum(f.stat().st_size for f in dest.iterdir()) / 1e6
    print(f"{tool['id']} → {dest} ({size:.1f} MB)")


if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if not a.startswith("--")]
    for t in TOOLS:
        if not want or t["id"] in want:
            build(t, "--force" in sys.argv)
