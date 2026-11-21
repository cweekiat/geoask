"""Local API + app server.  Run with ``geoask serve``.

    POST /api/chat       one chat with the chosen model (any provider) and every tool; photos and
                         a drawn box are optional; streams newline-delimited JSON events
    POST /api/run        run one tool directly (the map toolbar), no model involved
    GET/POST /api/settings, POST/DELETE /api/settings/key, POST /api/ollama/pull,
    POST /api/models/fetch    model choice, keys and offline model downloads

Chat events: session · photos · recorded · step · thinking · note · result · evidence ·
estimate · usage · answer · fly · error.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, aoi, mgrs
from . import settings as cfg
from .agent.catalog import catalog
from .agent.planner import EXAMPLES
from .models import list_models
from .tools import activity, investigate, superres, terrain
from .tools.embedding_change import embedding_change

WEB = Path(__file__).resolve().parents[2] / "web"
OUT = Path(os.environ.get("GEOASK_OUT", Path.home() / ".cache" / "geoask" / "results"))


class KeyIn(BaseModel):
    provider: str = "anthropic"
    key: str


class RunIn(BaseModel):
    tool: str
    args: dict = {}
    bbox: list[float] | None = None


class FetchIn(BaseModel):
    id: str


class PullIn(BaseModel):
    model: str


def _line(kind: str, **kw) -> str:
    return json.dumps({"type": kind, **kw}, default=str) + "\n"


def _stream(work) -> StreamingResponse:
    """Run ``work(emit)`` on a thread and stream what it emits."""
    q: queue.Queue = queue.Queue()

    def target():
        try:
            work(q.put)
        except Exception as e:  # noqa: BLE001 - every failure reaches the user
            q.put({"type": "error", "message": str(e) or type(e).__name__,
                   "hint": "Check the connection and the model in Settings, then try again."})
        finally:
            q.put(None)

    threading.Thread(target=target, daemon=True).start()

    def gen():
        while (ev := q.get()) is not None:
            yield json.dumps(ev, default=str) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


def provider_info() -> dict:
    p = cfg.resolve_provider()
    if p is None:
        return {"kind": "none", "label": "No model (rule-based)", "vision": False, "tools": False}
    return {"kind": p.kind, "label": p.label, "model": p.model, "vision": p.vision, "tools": p.tools}


def create_app() -> FastAPI:
    OUT.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="GeoAsk", version=__version__)

    def same_origin(request: Request) -> None:
        """Settings and keys change only from this app on this computer."""
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1] != request.headers.get("host", ""):
            raise HTTPException(403, "Requests from other sites can't change settings.")
        client = request.client.host if request.client else ""
        if client not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(403, "Settings can only be changed from this computer.")

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "live": True, "model": provider_info()}

    @app.get("/api/places")
    def places():
        return [{"name": k, "bbox": v, "approximate": True} for k, v in aoi.PLACES.items()]

    @app.get("/api/search")
    def search(q: str = "", online: bool = False):
        return [{"name": p.name, "bbox": p.bbox, "source": p.source,
                 "km2": round(p.area_km2, 1)} for p in aoi.search(q, online=online)]

    @app.get("/api/elevation")
    def elevation(lon: float, lat: float):
        return {"elevation_m": terrain.elevation_at(lon, lat), "source": terrain.SOURCE,
                "mgrs": mgrs.to_mgrs(lon, lat) if -80 <= lat <= 84 else None}

    @app.get("/api/line-of-sight")
    def los(lon1: float, lat1: float, lon2: float, lat2: float, h1: float = 2.0, h2: float = 2.0):
        return terrain.line_of_sight((lon1, lat1), (lon2, lat2), h1, h2)

    @app.get("/api/models")
    def models():
        return [asdict(s) | {"sensor_agnostic": s.sensor_agnostic} for s in list_models()]

    @app.get("/api/tools")
    def tools():
        return catalog()

    @app.get("/api/examples")
    def examples():
        return EXAMPLES

    # ---- settings -------------------------------------------------------------------------
    @app.get("/api/settings")
    def get_settings():
        from .models import enhance
        from .models.superres import FILES, MODELS_DIR

        s = cfg.load()
        return {"settings": s, "active": provider_info(),
                "keys": {k: cfg.masked(k) for k in cfg.SECRET_VARS},
                "ollama": cfg.ollama_status(s["ollama"]["host"]),
                "recommended": cfg.RECOMMENDED_OLLAMA,
                "offline": [
                    {"id": "sen2sr", "title": "SEN2SR-Lite (satellite super-resolution)", "size_mb": 3.4,
                     "licence": "CC0-1.0", "installed": all((MODELS_DIR / "sen2sr-lite" / f).exists() for f in FILES)},
                    {"id": "clay", "title": "Clay v1.5 encoder (any-change tool)", "size_mb": 5200,
                     "licence": "Apache-2.0", "installed": (MODELS_DIR / "clay-v1.5-encoder.pt").exists(),
                     "manual": "python scripts/fetch_clay.py"},
                    *[dict(e, title=e["title"] + " (photo enhancement)") for e in enhance.status()]]}

    @app.post("/api/settings")
    def post_settings(body: dict, request: Request):
        same_origin(request)
        cfg.save(body)
        return {"ok": True, "active": provider_info()}

    @app.post("/api/settings/key")
    def set_key(body: KeyIn, request: Request):
        from .geolocate import keys

        same_origin(request)
        if body.provider == "anthropic":
            key = keys.clean(body.key)
            if not keys.looks_valid(key):
                raise HTTPException(400, "That doesn't look like an Anthropic API key. It starts with sk-ant-.")
            try:
                keys.verify(key)
            except ValueError as e:
                raise HTTPException(400, str(e)) from e
        elif body.provider == "openai":
            key = body.key.strip()
        else:
            raise HTTPException(400, "Unknown provider.")
        cfg.save_secret(body.provider, key)
        return {"ok": True, "key": cfg.masked(body.provider), "active": provider_info()}

    @app.delete("/api/settings/key")
    def delete_key(request: Request, provider: str = "anthropic"):
        same_origin(request)
        if provider not in cfg.SECRET_VARS:
            raise HTTPException(400, "Unknown provider.")
        cfg.remove_secret(provider)
        return {"ok": True, "active": provider_info()}

    @app.post("/api/ollama/pull")
    def ollama_pull(body: PullIn, request: Request):
        same_origin(request)
        host = cfg.load()["ollama"]["host"].rstrip("/")

        def work(emit):
            req = urllib.request.Request(f"{host}/api/pull", data=json.dumps({"model": body.model}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3600) as r:
                for line in r:
                    ev = json.loads(line)
                    done, total = ev.get("completed"), ev.get("total")
                    pct = f" {100 * done / total:.0f}%" if done and total else ""
                    emit({"type": "step", "text": f"{ev.get('status', '')}{pct}"})
            emit({"type": "done", "model": body.model})

        return _stream(work)

    @app.post("/api/models/fetch")
    def fetch_model(body: FetchIn, request: Request):
        same_origin(request)

        def work(emit):
            step = lambda m: emit({"type": "step", "text": m})
            if body.id == "sen2sr":
                from .models.superres import fetch_sen2sr

                step("Downloading SEN2SR-Lite (3.4 MB)")
                fetch_sen2sr()
            elif body.id in ("realesrgan-x4", "sd-x4-upscaler"):
                from .models import enhance

                enhance.fetch(body.id, step)
            else:
                raise ValueError("This model is installed from the command line (see Settings).")
            emit({"type": "done", "id": body.id})

        return _stream(work)

    @app.get("/api/models/size")
    def model_size(id: str):
        from .models import enhance

        if id == "sd-x4-upscaler":
            return {"size_mb": enhance.sd_size_mb()}
        raise HTTPException(404)

    # ---- the chat ---------------------------------------------------------------------------
    @app.post("/api/chat")
    async def chat_endpoint(message: Annotated[str, Form()] = "", session: Annotated[str, Form()] = "",
                            bbox: Annotated[str, Form()] = "",
                            files: Annotated[list[UploadFile] | None, File()] = None):
        from .agent import chat
        from .geolocate import images as li

        raw = [(f.filename or "", await f.read()) for f in (files or [])[: li.MAX_PHOTOS]]
        sel = json.loads(bbox) if bbox else None
        s = cfg.load()

        def work(emit):
            sid, _ = chat.session(session or None)
            emit({"type": "session", "id": sid})
            photos = [li.load(data, i, name) for i, (name, data) in enumerate(raw, 1)]
            if photos:
                emit({"type": "photos", "photos": [{"name": p.name, "thumb": p.thumb_b64, "meta": p.meta}
                                                   for p in photos]})
                gps = [p for p in photos if p.meta.get("gps")]
                if gps:  # non-AI answer first: the camera recorded where it was
                    emit({"type": "recorded", "points": [dict(p.meta["gps"]) for p in gps]})
            provider = cfg.resolve_provider(s)
            if provider is None:
                if photos:
                    emit({"type": "answer", "source": "rule-based (no model)", "unverified": [],
                          "text": "Photo geolocation needs a model. Open Settings to connect Claude, "
                                  "Ollama or another model."})
                    return
                chat.run_without_model(sid, message, sel, OUT, emit)
                return
            emit({"type": "model", "label": provider.label, "vision": provider.vision})
            chat.run_turn(provider, sid, message, photos, sel, OUT, emit,
                          share_meta=bool(s.get("share_photo_details", True)))

        return _stream(work)

    @app.post("/api/run")
    def run_tool(body: RunIn):
        """The map toolbar: run one tool on the drawn box or a point, without a model."""
        from .agent import chat

        def work(emit):
            r = chat.run_analysis(body.tool, body.args, body.bbox, OUT, emit)
            if r.get("id"):
                r["base"] = f"/outputs/{r['id']}/"
            emit({"type": "result", "result": r})
            emit({"type": "done"})

        return _stream(work)

    @app.post("/api/enhance")
    async def enhance_endpoint(file: Annotated[UploadFile, File()], guidance: Annotated[str, Form()] = ""):
        """The toolbar's generative enhancement: one photo, optional text guidance, no model."""
        from .geolocate import images as li
        from .models import enhance

        data = await file.read()

        def work(emit):
            photo = li.load(data, 1, file.filename or "")
            r = enhance.enhance_photo(photo, guidance, OUT, progress=lambda m: emit({"type": "step", "text": m}))
            r["base"] = f"/outputs/{r['id']}/"
            emit({"type": "result", "result": r})

        return _stream(work)

    app.mount("/outputs", StaticFiles(directory=OUT), name="outputs")
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app


def _run(tool: str, args: dict):
    """Run a planned tool on a worker thread; yield ("step", msg)… then ("result", dict).
    Used by the no-model chat path and by scripts/build_gallery.py."""
    q: queue.Queue = queue.Queue()
    box: dict = {}
    bbox = tuple(args["bbox"]) if args.get("bbox") else None

    def work():
        try:
            if tool == "activity":
                box["result"] = activity.activity(args["place"], args["window"], OUT, progress=q.put, bbox=bbox)
            elif tool == "super_resolve":
                box["result"] = superres.super_resolve(args["place"], args["window"], OUT, args["model"],
                                                       progress=q.put, bbox=bbox)
            elif tool == "terrain":
                box["result"] = terrain.terrain(args["place"], OUT, progress=q.put, bbox=bbox)
            elif tool == "viewshed":
                box["result"] = terrain.viewshed(args["lon"], args["lat"], OUT, args["radius_m"],
                                                 args["observer_h"], args["target_h"], progress=q.put)
            elif tool == "embedding_change":
                box["result"] = embedding_change(args["place"], args["t0"], args["t1"], OUT,
                                                 model=args["model"], progress=q.put, bbox=bbox)
            else:
                box["result"] = investigate.index_change(args["place"], args["index"], args["t0"],
                                                         args["t1"], OUT, progress=q.put, bbox=bbox)
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
