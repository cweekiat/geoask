"""Solar position (NOAA algorithm, accurate to well under a degree), so the agent can test a
candidate place and time against the shadows it sees: the sun's azimuth gives the shadow
direction, its elevation gives the shadow length (shadow ≈ height / tan(elevation))."""

from __future__ import annotations

import math
from datetime import datetime, timezone


def solar_position(lat: float, lon: float, when: datetime) -> dict:
    """Azimuth (degrees clockwise from north) and elevation (degrees) of the sun."""
    t = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
    jd = t.timestamp() / 86400 + 2440587.5
    jc = (jd - 2451545) / 36525
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(2 * mr) * (0.019993 - 0.000101 * jc) + math.sin(3 * mr) * 0.000289)
    lam = l0 + c - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * jc))
    eps0 = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(math.radians(125.04 - 1934.136 * jc))
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lam))))
    y = math.tan(math.radians(eps / 2)) ** 2
    l0r = math.radians(l0)
    eqt = 4 * math.degrees(y * math.sin(2 * l0r) - 2 * e * math.sin(mr)
                           + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
                           - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))
    minutes = t.hour * 60 + t.minute + t.second / 60
    tst = (minutes + eqt + 4 * lon) % 1440
    ha = tst / 4 - 180 if tst / 4 >= 0 else tst / 4 + 180
    latr, dr, har = math.radians(lat), math.radians(decl), math.radians(ha)
    cosz = math.sin(latr) * math.sin(dr) + math.cos(latr) * math.cos(dr) * math.cos(har)
    zen = math.degrees(math.acos(max(-1.0, min(1.0, cosz))))
    elev = 90 - zen
    denom = math.cos(latr) * math.sin(math.radians(zen))
    if abs(denom) < 1e-9:
        az = 0.0
    else:
        a = (math.sin(latr) * math.cos(math.radians(zen)) - math.sin(dr)) / denom
        az = math.degrees(math.acos(max(-1.0, min(1.0, a))))
        az = (az + 180) % 360 if ha > 0 else (540 - az) % 360
    shadow = None if elev <= 0 else round(1 / math.tan(math.radians(elev)), 2)
    return {"azimuth_deg": round(az, 1), "elevation_deg": round(elev, 1),
            "shadow_azimuth_deg": round((az + 180) % 360, 1),
            "shadow_length_per_m_height": shadow, "declination_deg": round(decl, 2),
            "daylight": elev > -0.83}
