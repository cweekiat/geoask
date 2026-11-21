"""The web app's geo.js must agree with mgrs.py (needs Node; skipped without it)."""

import json
import math
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from geoask import mgrs

GEO_JS = Path(__file__).resolve().parents[1] / "web" / "app" / "geo.js"


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node.js")
def test_geo_js_matches_python():
    rnd = random.Random(7)
    pts = [(rnd.uniform(-179.9, 179.9), rnd.uniform(-79.9, 83.9)) for _ in range(500)]
    pts += [(103.8198, 1.3521), (-77.0353, 38.8895), (5.3, 60.4), (15.0, 78.2), (151.21, -33.86)]
    js = (f"const G=require({json.dumps(str(GEO_JS))});const P={json.dumps(pts)};"
          "console.log(JSON.stringify(P.map(([x,y])=>[G.toMGRS(x,y,5),G.fromMGRS(G.toMGRS(x,y,5)),"
          "G.inverse(103.8,1.3,103.9,1.4)])))")
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True,
                                    check=True).stdout)
    for (lon, lat), (ref, back, _) in zip(pts, out):
        assert ref == mgrs.to_mgrs(lon, lat), (lon, lat)
        plon, plat = mgrs.from_mgrs(ref)
        assert abs(back[0] - plon) < 1e-7 and abs(back[1] - plat) < 1e-7
    d = out[0][2]  # ~15.7 km NE across Singapore
    assert 15_600 < d["m"] < 15_800 and 44 < d["bearing"] < 46


def test_mgrs_round_trip_and_parsing():
    rnd = random.Random(1)
    for _ in range(2000):
        lon, lat = rnd.uniform(-179.9, 179.9), rnd.uniform(-79.9, 83.9)
        lo, la = mgrs.from_mgrs(mgrs.to_mgrs(lon, lat))
        # the reference names the 1 m square's corner, so the round trip is within ~1.5 m
        assert math.hypot((lo - lon) * 111_320 * math.cos(math.radians(lat)),
                          (la - lat) * 110_570) < 2
    assert mgrs.to_mgrs(5.3, 60.4).startswith("32V")  # Norway exception
    assert mgrs.to_mgrs(15.0, 78.2).startswith("33X")  # Svalbard exception
    lon, lat = mgrs.parse_coordinates("1.3521, 103.8198")
    assert (lon, lat) == (103.8198, 1.3521)
    lon, lat = mgrs.parse_coordinates(mgrs.to_mgrs(103.8198, 1.3521))
    assert abs(lon - 103.8198) < 1e-4 and abs(lat - 1.3521) < 1e-4
    assert mgrs.parse_coordinates("Tengah") is None
