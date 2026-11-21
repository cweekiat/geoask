"""Scene search on public STAC catalogues. No API keys.

Planetary Computer assets need a short-lived SAS token, which its public endpoint hands out
anonymously, so there's still no account and no key.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pystac_client import Client

from ..aoi import BBox
from ..profiles import InstrumentProfile


@dataclass
class Scene:
    id: str
    datetime: datetime
    cloud_cover: float | None  # whole-scene value from metadata
    item: Any  # pystac.Item
    profile: InstrumentProfile

    def href(self, asset: str) -> str:
        return self.item.assets[asset].href

    @property
    def date(self) -> str:
        return self.datetime.strftime("%Y-%m-%d")


_tokens: dict[str, tuple[str, float]] = {}


def _pc_token(collection: str) -> str:
    tok, exp = _tokens.get(collection, ("", 0.0))
    if time.time() < exp - 60:
        return tok
    url = f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.load(r)
    tok = data["token"]
    exp_s = data.get("msft:expiry", "")
    try:
        exp = datetime.fromisoformat(exp_s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        exp = time.time() + 1800
    _tokens[collection] = (tok, exp)
    return tok


def _sign(item: Any, profile: InstrumentProfile) -> Any:
    if profile.stac.get("signing") != "planetary-computer":
        return item
    tok = _pc_token(profile.stac["collection"])
    for a in item.assets.values():
        parsed = urllib.parse.urlparse(a.href)
        if parsed.scheme.startswith("http") and "sig=" not in (parsed.query or ""):
            a.href = f"{a.href}{'&' if parsed.query else '?'}{tok}"
    return item


def find_scenes(
    profile: InstrumentProfile,
    bbox: BBox,
    start: str,
    end: str,
    max_cloud: float | None = 80,
    limit: int = 100,
) -> list[Scene]:
    """Search ``profile``'s STAC collection. Returns scenes sorted by date (oldest first)."""
    s = profile.stac
    client = Client.open(s["url"])
    query = {}
    cprop = s.get("cloud_property")
    if cprop and max_cloud is not None:
        query[cprop] = {"lt": max_cloud}
    search = client.search(
        collections=[s["collection"]],
        bbox=bbox,
        datetime=f"{start}/{end}",
        query=query or None,
        max_items=limit,
    )
    scenes = []
    for it in search.items():
        it = _sign(it, profile)
        scenes.append(
            Scene(
                id=it.id,
                datetime=it.datetime,
                cloud_cover=it.properties.get(cprop) if cprop else None,
                item=it,
                profile=profile.with_item(it),
            )
        )
    scenes.sort(key=lambda sc: sc.datetime)
    return scenes


def group_by_date(scenes: list[Scene]) -> dict[str, list[Scene]]:
    """Same-day acquisitions (adjacent tiles of one pass) are mosaicked together."""
    out: dict[str, list[Scene]] = {}
    for sc in scenes:
        out.setdefault(sc.date, []).append(sc)
    return out
