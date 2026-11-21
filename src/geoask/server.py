"""Local API + static app server.  Run with ``geoask serve``.

``/api/ask`` takes a free-form question (and optionally a box drawn on the map) and streams
newline-delimited JSON events:

    plan → step… → result → answer      (an analysis)
    clarify | reply | error              (no analysis)

The planner is Qwen 2.5 7B via Ollama when it's running, otherwise the rule-based planner.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, aoi
from .agent import answer, llm
from .agent.planner import EXAMPLES, Clarify, Plan, Reply, default_planner
from .models import ModelNotInstalled, list_models
from .tools import investigate
from .tools.embedding_change import embedding_change

WEB = Path(__file__).resolve().parents[2] / "web"
OUT = Path(os.environ.get("GEOASK_OUT", Path.home() / ".cache" / "geoask" / "results"))


class Ask(BaseModel):
    question: str
    bbox: list[float] | None = None  # [west, south, east, north] drawn on the map


_planner_cache: tuple[float, object] = (0.0, None)


def planner():
    """Re-check Ollama at most every 30 s, so starting it later just works."""
    global _planner_cache
    t, p = _planner_cache
    if p is None or time.time() - t > 30:
        _planner_cache = (time.time(), default_planner())
    return _planner_cache[1]


def create_app() -> FastAPI:
    OUT.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="GeoAsk", version=__version__)

    @app.get("/api/health")
    def health():
        p = planner()
        return {"ok": True, "version": __version__, "planner": p.name, "live": True,
                "llm": llm.MODEL if p.name.startswith("ollama") else None}

    @app.get("/api/places")
    def places():
        return [{"name": k, "bbox": v, "approximate": True} for k, v in aoi.PLACES.items()]

    @app.get("/api/search")
    def search(q: str = "", online: bool = False):
        """Bundled names as you type; ``online=true`` (on Enter) adds the worldwide geocoder."""
        return [{"name": p.name, "bbox": p.bbox, "source": p.source,
                 "km2": round(p.area_km2, 1)} for p in aoi.search(q, online=online)]

    @app.get("/api/models")
    def models():
        return [asdict(s) | {"sensor_agnostic": s.sensor_agnostic} for s in list_models()]

    @app.get("/api/examples")
    def examples():
        return EXAMPLES

    @app.post("/api/ask")
    def ask(body: Ask):
        def emit(kind: str, **kw) -> str:
            return json.dumps({"type": kind, **kw}, default=str) + "\n"

        def events():
            p = planner()
            yield emit("step", text=f"Reading the question ({p.name})")
            out = p.plan(body.question, selection=tuple(body.bbox) if body.bbox else None)
            if isinstance(out, Clarify):
                yield emit("clarify", message=out.message, suggestions=out.suggestions,
                           bbox=out.bbox)
                return
            if isinstance(out, Reply):
                yield emit("reply", message=out.message, planner=out.planner,
                           suggestions=EXAMPLES)
                return
            assert isinstance(out, Plan)
            yield emit("plan", tool=out.tool, args=out.args, explanation=out.explanation,
                       planner=out.planner)
            try:
                result = None
                for kind, payload in _run(out.tool, out.args):
                    if kind == "step":
                        yield emit("step", text=payload)
                    else:
                        result = payload
                        result["base"] = f"/outputs/{result['id']}/"
                        yield emit("result", result=result)
                if result is not None:
                    if out.planner.startswith("ollama"):
                        yield emit("step", text="Writing the answer from the measurements")
                        text, source = answer.write(body.question, result)
                    else:
                        text, source = answer.template_answer(result), "template"
                    yield emit("answer", text=text, source=source)
            except investigate.NoClearDate as e:
                yield emit("error", message=str(e),
                           hint="Try a wider time range or a different year.")
            except ModelNotInstalled as e:
                yield emit("error", message=str(e),
                           hint="Ask about vegetation, water or built-up land to use the "
                                "spectral tools, which need no model.")
            except Exception as e:  # noqa: BLE001 - surface every failure to the user
                yield emit("error", message=f"{type(e).__name__}: {e}",
                           hint="Check your internet connection, then try again.")

        return StreamingResponse(events(), media_type="application/x-ndjson")

    app.mount("/outputs", StaticFiles(directory=OUT), name="outputs")
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app


def _run(tool: str, args: dict):
    """Run the tool on a worker thread; yield ("step", msg)… then ("result", dict)."""
    q: queue.Queue = queue.Queue()
    box: dict = {}
    bbox = tuple(args["bbox"]) if args.get("bbox") else None

    def work():
        try:
            if tool == "embedding_change":
                box["result"] = embedding_change(
                    args["place"], args["t0"], args["t1"], OUT, model=args["model"],
                    progress=q.put, bbox=bbox)
            else:
                box["result"] = investigate.index_change(
                    args["place"], args["index"], args["t0"], args["t1"], OUT,
                    progress=q.put, bbox=bbox)
        except Exception as e:  # noqa: BLE001
            box["error"] = e
        finally:
            q.put(None)

    threading.Thread(target=work, daemon=True).start()
    while (msg := q.get()) is not None:
        yield "step", msg
    if "error" in box:
        raise box["error"]
    yield "result", box["result"]
