"""Record one real Locate run for the Pages demo (web/gallery/locate/).

Runs the actual Claude agent (needs ANTHROPIC_API_KEY; costs one run) on an openly licensed photo
and saves the photo, its credit and every event, so Demo mode replays exactly what happened.

    python scripts/record_locate.py PHOTO_URL "credit line" [--model sonnet|haiku]
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from geoask.geolocate import agent, images
from geoask.geolocate.sources import UA

OUT = Path(__file__).resolve().parents[1] / "web" / "gallery" / "locate"


def main() -> None:
    url, credit = sys.argv[1], sys.argv[2]
    model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "sonnet"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        data = r.read()
    photo = images.load(data, 1, "photo.jpg")
    OUT.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    t0 = time.time()

    def emit(ev: dict) -> None:
        events.append({"t": round(time.time() - t0, 2), **ev})
        print(ev.get("type"), (ev.get("text") or "")[:90])

    est = agent.locate([photo], emit, model=model, share_meta=False)
    import base64

    (OUT / "photo.jpg").write_bytes(base64.b64decode(photo.jpeg_b64))
    (OUT / "run.json").write_text(json.dumps({
        "photo": "photo.jpg", "credit": credit, "source_url": url, "model": est["model"],
        "seconds": round(time.time() - t0, 1), "events": events}, indent=1, default=str))
    print(f"\n{est['summary']} · {est['cost_usd']} USD · {est['rounds']} rounds → {OUT}")


if __name__ == "__main__":
    main()
