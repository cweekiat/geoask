"""Local API + static app server.  Run with ``geoask serve``.

The browser app talks to this over plain JSON. ``/api/ask`` streams newline-delimited JSON events
(plan → step… → result | clarify | error) so the UI can show specific progress while tools run.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, aoi
from .agent.planner import EXAMPLES, Clarify, RuleBasedPlanner
from .models import list_models
from .tools import investigate

WEB = Path(__file__).resolve().parents[2] / "web"
OUT = Path(os.environ.get("GEOASK_OUT", Path.home() / ".cache" / "geoask" / "results"))


class Ask(BaseModel):
    question: str


def create_app() -> FastAPI:
    OUT.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="GeoAsk", version=__version__)
    planner = RuleBasedPlanner()

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "planner": planner.name, "live": True}

    @app.get("/api/places")
    def places():
        return [{"name": k, "bbox": v, "approximate": True}
                for k, v in aoi.PLACES.items()]

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
            plan = planner.plan(body.question)
            if isinstance(plan, Clarify):
                yield emit("clarify", message=plan.message, suggestions=plan.suggestions)
                return
            yield emit("plan", tool=plan.tool, args=plan.args, explanation=plan.explanation,
                       planner=plan.planner)
            try:
                for kind, payload in _run(plan.args):
                    if kind == "step":
                        yield emit("step", text=payload)
                    else:
                        payload["base"] = f"/outputs/{payload['id']}/"
                        yield emit("result", result=payload)
            except investigate.NoClearDate as e:
                yield emit("error", message=str(e),
                           hint="Try a wider time range or a different year.")
            except Exception as e:  # noqa: BLE001 - surface every failure to the user
                yield emit("error", message=f"{type(e).__name__}: {e}",
                           hint="Check your internet connection, then try again.")

        return StreamingResponse(events(), media_type="application/x-ndjson")

    app.mount("/outputs", StaticFiles(directory=OUT), name="outputs")
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")

    return app


def _run(args: dict):
    """Run the tool on a worker thread; yield ("step", msg)… then ("result", dict)."""
    q: queue.Queue = queue.Queue()
    box: dict = {}

    def work():
        try:
            box["result"] = investigate.index_change(
                args["place"], args["index"], args["t0"], args["t1"], OUT,
                progress=lambda m: q.put(m))
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
