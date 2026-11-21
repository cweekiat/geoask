"""MGRS (Military Grid Reference System) and UTM coordinates, WGS84.

    to_mgrs(lon, lat, precision=5)  -> "33U VU 12345 67890"   (precision 5 = 1 m, 4 = 10 m, ...)
    from_mgrs("33UVU1234567890")    -> (lon, lat) of the square's south-west corner
    parse_coordinates(text)         -> (lon, lat) from "1.35, 103.8", "48N 366000 149000" or MGRS

Polar regions (UPS, beyond 84° N / 80° S) are not supported. The web app uses the same rules in
``web/app/geo.js``; ``tests/test_mgrs.py`` checks both against known points.
"""

from __future__ import annotations

import math
import re

BANDS = "CDEFGHJKLMNPQRSTUVWX"  # 8° latitude bands from 80° S; X spans 72–84° N
COLS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")  # 100 km columns, by zone % 3
ROWS = "ABCDEFGHJKLMNPQRSTUV"  # 100 km rows, repeating every 2,000 km

# Transverse Mercator by Krüger's series (Karney 2011, to n^6): sub-millimetre inside a zone.
_A, _F, _K0 = 6378137.0, 1 / 298.257223563, 0.9996
_N = _F / (2 - _F)
_AA = _A / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64 + _N**6 / 256)
_ALPHA = (_N / 2 - 2 * _N**2 / 3 + 5 * _N**3 / 16 + 41 * _N**4 / 180 - 127 * _N**5 / 288
          + 7891 * _N**6 / 37800,
          13 * _N**2 / 48 - 3 * _N**3 / 5 + 557 * _N**4 / 1440 + 281 * _N**5 / 630
          - 1983433 * _N**6 / 1935360,
          61 * _N**3 / 240 - 103 * _N**4 / 140 + 15061 * _N**5 / 26880 + 167603 * _N**6 / 181440,
          49561 * _N**4 / 161280 - 179 * _N**5 / 168 + 6601661 * _N**6 / 7257600,
          34729 * _N**5 / 80640 - 3418889 * _N**6 / 1995840,
          212378941 * _N**6 / 319334400)
_BETA = (_N / 2 - 2 * _N**2 / 3 + 37 * _N**3 / 96 - _N**4 / 360 - 81 * _N**5 / 512
         + 96199 * _N**6 / 604800,
         _N**2 / 48 + _N**3 / 15 - 437 * _N**4 / 1440 + 46 * _N**5 / 105
         - 1118711 * _N**6 / 3870720,
         17 * _N**3 / 480 - 37 * _N**4 / 840 - 209 * _N**5 / 4480 + 5569 * _N**6 / 90720,
         4397 * _N**4 / 161280 - 11 * _N**5 / 504 - 830251 * _N**6 / 7257600,
         4583 * _N**5 / 161280 - 108847 * _N**6 / 3991680,
         20648693 * _N**6 / 638668800)
_E = math.sqrt(_F * (2 - _F))


def _tm_forward(lon: float, lat: float, lon0: float) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon - lon0)
    t = math.sinh(math.atanh(math.sin(phi)) - _E * math.atanh(_E * math.sin(phi)))
    xi_, eta_ = math.atan2(t, math.cos(lam)), math.asinh(math.sin(lam) / math.hypot(t, math.cos(lam)))
    xi = xi_ + sum(a * math.sin(2 * j * xi_) * math.cosh(2 * j * eta_)
                   for j, a in enumerate(_ALPHA, 1))
    eta = eta_ + sum(a * math.cos(2 * j * xi_) * math.sinh(2 * j * eta_)
                     for j, a in enumerate(_ALPHA, 1))
    return _K0 * _AA * eta, _K0 * _AA * xi


def _tm_inverse(x: float, y: float, lon0: float) -> tuple[float, float]:
    xi, eta = y / (_K0 * _AA), x / (_K0 * _AA)
    xi_ = xi - sum(b * math.sin(2 * j * xi) * math.cosh(2 * j * eta) for j, b in enumerate(_BETA, 1))
    eta_ = eta - sum(b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
                     for j, b in enumerate(_BETA, 1))
    tau_ = math.sin(xi_) / math.hypot(math.sinh(eta_), math.cos(xi_))
    tau = tau_
    for _ in range(6):  # Newton on tau (Karney eq. 19–21)
        sig = math.sinh(_E * math.atanh(_E * tau / math.sqrt(1 + tau * tau)))
        ti = tau * math.sqrt(1 + sig * sig) - sig * math.sqrt(1 + tau * tau)
        d = (tau_ - ti) / math.sqrt(1 + ti * ti) * (1 + (1 - _E * _E) * tau * tau) / (
            (1 - _E * _E) * math.sqrt(1 + tau * tau))
        tau += d
        if abs(d) < 1e-12:
            break
    lat = math.degrees(math.atan(tau))
    lon = lon0 + math.degrees(math.atan2(math.sinh(eta_), math.cos(xi_)))
    return lon, lat


def _utm_forward(lon: float, lat: float, z: int, south: bool) -> tuple[float, float]:
    x, y = _tm_forward(lon, lat, -183 + 6 * z)
    return x + 500_000, y + (10_000_000 if south else 0)


def _utm_inverse(e: float, n: float, z: int, south: bool) -> tuple[float, float]:
    return _tm_inverse(e - 500_000, n - (10_000_000 if south else 0), -183 + 6 * z)


def zone_for(lon: float, lat: float) -> int:
    lon = (lon + 180) % 360 - 180
    z = int((lon + 180) // 6) + 1
    if 56 <= lat < 64 and 3 <= lon < 12:  # Norway
        z = 32
    if 72 <= lat < 84 and lon >= 0:  # Svalbard
        z = 31 if lon < 9 else 33 if lon < 21 else 35 if lon < 33 else 37 if lon < 42 else z
    return min(z, 60)


def band_for(lat: float) -> str:
    if not -80 <= lat <= 84:
        raise ValueError("MGRS covers 80° S to 84° N (beyond that is UPS)")
    return BANDS[min(int((lat + 80) // 8), 19)]


def to_utm(lon: float, lat: float) -> tuple[int, str, float, float]:
    """(zone, 'N' | 'S', easting, northing)."""
    z = zone_for(lon, lat)
    hemi = "N" if lat >= 0 else "S"
    e, n = _utm_forward(lon, lat, z, hemi == "S")
    return z, hemi, e, n


def to_mgrs(lon: float, lat: float, precision: int = 5) -> str:
    if not 0 <= precision <= 5:
        raise ValueError("precision is 0–5 digits")
    z, _, e, n = to_utm(lon, lat)
    band = band_for(lat)
    col = COLS[(z - 1) % 3][int(e // 100_000) - 1]
    row = ROWS[(int(n // 100_000) + (5 if z % 2 == 0 else 0)) % 20]
    d = 10 ** (5 - precision)
    ee, nn = int(e % 100_000) // d, int(n % 100_000) // d
    digits = f" {ee:0{precision}d} {nn:0{precision}d}" if precision else ""
    return f"{z}{band} {col}{row}{digits}"


_MGRS = re.compile(r"^\s*(\d{1,2})\s*([C-HJ-NP-X])\s*([A-HJ-NP-Z])([A-HJ-NP-V])\s*"
                   r"(\d*)\s*(\d*)\s*$", re.IGNORECASE)


def from_mgrs(ref: str) -> tuple[float, float]:
    m = _MGRS.match(ref)
    if not m:
        raise ValueError(f"not an MGRS reference: {ref!r}")
    z, band, col, row, a, b = m.groups()
    z, band, col, row = int(z), band.upper(), col.upper(), row.upper()
    digits = a + b if not b else None
    if digits is not None:  # "33UVU1234567890": one run of digits, split in half
        if len(digits) % 2:
            raise ValueError("MGRS easting and northing need the same number of digits")
        a, b = digits[: len(digits) // 2], digits[len(digits) // 2:]
    if len(a) != len(b) or len(a) > 5:
        raise ValueError("MGRS easting and northing need the same number of digits (≤ 5)")
    scale = 10 ** (5 - len(a)) if a else 0
    e100 = COLS[(z - 1) % 3].index(col) + 1
    n100 = (ROWS.index(row) - (5 if z % 2 == 0 else 0)) % 20
    east = e100 * 100_000 + (int(a) * scale if a else 0)
    north = n100 * 100_000 + (int(b) * scale if b else 0)
    south = BANDS.index(band) < BANDS.index("N")
    band_lat = -80 + 8 * BANDS.index(band)
    _, n_min = _utm_forward(-183 + 6 * z, band_lat, z, south)
    while north < n_min - 100_000:  # rows repeat every 2,000 km: lift into the latitude band
        north += 2_000_000
    return _utm_inverse(east, north, z, south)


_LATLON = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$")
_UTM = re.compile(r"^\s*(\d{1,2})\s*([NS])\s+(\d+(?:\.\d+)?)\s*[mE]*\s+(\d+(?:\.\d+)?)\s*[mN]*\s*$",
                  re.IGNORECASE)


def parse_coordinates(text: str) -> tuple[float, float] | None:
    """Lat/lon ("1.35, 103.82"), UTM ("48N 366000 149000") or MGRS → (lon, lat); else None."""
    if m := _LATLON.match(text):
        lat, lon = float(m[1]), float(m[2])
        return (lon, lat) if -90 <= lat <= 90 and -180 <= lon <= 180 else None
    if m := _UTM.match(text):
        return _utm_inverse(float(m[3]), float(m[4]), int(m[1]), m[2].upper() == "S")
    try:
        return from_mgrs(text)
    except ValueError:
        return None
