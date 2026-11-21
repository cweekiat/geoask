/* GeoAsk coordinate maths: UTM, MGRS, coordinate parsing, geodesic distance and bearing (WGS84).
   Same rules as src/geoask/mgrs.py; tests/test_geo_js.py runs both on the same points.
   UTM uses Krüger's series (Karney 2011): sub-millimetre inside a zone. No dependencies. */
(function (root) {
  'use strict';
  const A = 6378137, F = 1 / 298.257223563, K0 = 0.9996;
  const N = F / (2 - F), E = Math.sqrt(F * (2 - F));
  const AA = A / (1 + N) * (1 + N ** 2 / 4 + N ** 4 / 64 + N ** 6 / 256);
  const ALPHA = [
    N / 2 - 2 * N ** 2 / 3 + 5 * N ** 3 / 16 + 41 * N ** 4 / 180 - 127 * N ** 5 / 288 + 7891 * N ** 6 / 37800,
    13 * N ** 2 / 48 - 3 * N ** 3 / 5 + 557 * N ** 4 / 1440 + 281 * N ** 5 / 630 - 1983433 * N ** 6 / 1935360,
    61 * N ** 3 / 240 - 103 * N ** 4 / 140 + 15061 * N ** 5 / 26880 + 167603 * N ** 6 / 181440,
    49561 * N ** 4 / 161280 - 179 * N ** 5 / 168 + 6601661 * N ** 6 / 7257600,
    34729 * N ** 5 / 80640 - 3418889 * N ** 6 / 1995840,
    212378941 * N ** 6 / 319334400];
  const BETA = [
    N / 2 - 2 * N ** 2 / 3 + 37 * N ** 3 / 96 - N ** 4 / 360 - 81 * N ** 5 / 512 + 96199 * N ** 6 / 604800,
    N ** 2 / 48 + N ** 3 / 15 - 437 * N ** 4 / 1440 + 46 * N ** 5 / 105 - 1118711 * N ** 6 / 3870720,
    17 * N ** 3 / 480 - 37 * N ** 4 / 840 - 209 * N ** 5 / 4480 + 5569 * N ** 6 / 90720,
    4397 * N ** 4 / 161280 - 11 * N ** 5 / 504 - 830251 * N ** 6 / 7257600,
    4583 * N ** 5 / 161280 - 108847 * N ** 6 / 3991680,
    20648693 * N ** 6 / 638668800];
  const rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI;

  function tmForward(lon, lat, lon0) {
    const phi = rad(lat), lam = rad(lon - lon0);
    const t = Math.sinh(Math.atanh(Math.sin(phi)) - E * Math.atanh(E * Math.sin(phi)));
    const xi_ = Math.atan2(t, Math.cos(lam)), eta_ = Math.asinh(Math.sin(lam) / Math.hypot(t, Math.cos(lam)));
    let xi = xi_, eta = eta_;
    ALPHA.forEach((a, i) => { const j = 2 * (i + 1); xi += a * Math.sin(j * xi_) * Math.cosh(j * eta_); eta += a * Math.cos(j * xi_) * Math.sinh(j * eta_); });
    return [K0 * AA * eta, K0 * AA * xi];
  }
  function tmInverse(x, y, lon0) {
    const xi = y / (K0 * AA), eta = x / (K0 * AA);
    let xi_ = xi, eta_ = eta;
    BETA.forEach((b, i) => { const j = 2 * (i + 1); xi_ -= b * Math.sin(j * xi) * Math.cosh(j * eta); eta_ -= b * Math.cos(j * xi) * Math.sinh(j * eta); });
    const tau_ = Math.sin(xi_) / Math.hypot(Math.sinh(eta_), Math.cos(xi_));
    let tau = tau_;
    for (let k = 0; k < 6; k++) {
      const sig = Math.sinh(E * Math.atanh(E * tau / Math.sqrt(1 + tau * tau)));
      const ti = tau * Math.sqrt(1 + sig * sig) - sig * Math.sqrt(1 + tau * tau);
      const d = (tau_ - ti) / Math.sqrt(1 + ti * ti) * (1 + (1 - E * E) * tau * tau) / ((1 - E * E) * Math.sqrt(1 + tau * tau));
      tau += d; if (Math.abs(d) < 1e-12) break;
    }
    return [lon0 + deg(Math.atan2(Math.sinh(eta_), Math.cos(xi_))), deg(Math.atan(tau))];
  }

  const BANDS = 'CDEFGHJKLMNPQRSTUVWX', COLS = ['ABCDEFGH', 'JKLMNPQR', 'STUVWXYZ'], ROWS = 'ABCDEFGHJKLMNPQRSTUV';
  const cm = z => -183 + 6 * z;
  function zoneFor(lon, lat) {
    lon = ((lon + 180) % 360 + 360) % 360 - 180;
    let z = Math.floor((lon + 180) / 6) + 1;
    if (lat >= 56 && lat < 64 && lon >= 3 && lon < 12) z = 32;
    if (lat >= 72 && lat < 84 && lon >= 0) z = lon < 9 ? 31 : lon < 21 ? 33 : lon < 33 ? 35 : lon < 42 ? 37 : z;
    return Math.min(z, 60);
  }
  const bandFor = lat => (lat < -80 || lat > 84) ? null : BANDS[Math.min(Math.floor((lat + 80) / 8), 19)];
  function utmForward(lon, lat, z = zoneFor(lon, lat), south = lat < 0) {
    const [x, y] = tmForward(lon, lat, cm(z));
    return { zone: z, hemi: south ? 'S' : 'N', e: x + 500000, n: y + (south ? 10000000 : 0) };
  }
  const utmInverse = (e, n, z, south) => tmInverse(e - 500000, n - (south ? 10000000 : 0), cm(z));

  function toMGRS(lon, lat, precision = 5) {
    const band = bandFor(lat); if (!band) return null;
    const { zone: z, e, n } = utmForward(lon, lat);
    const col = COLS[(z - 1) % 3][Math.floor(e / 100000) - 1];
    const row = ROWS[(Math.floor(n / 100000) + (z % 2 === 0 ? 5 : 0)) % 20];
    const d = 10 ** (5 - precision), pad = v => String(Math.floor((v % 100000) / d)).padStart(precision, '0');
    return `${z}${band} ${col}${row}` + (precision ? ` ${pad(e)} ${pad(n)}` : '');
  }
  /** 100 km square ID ("VU") for a UTM position in zone z. */
  function square(z, e, n) {
    const c = COLS[(z - 1) % 3][Math.floor(e / 100000) - 1];
    return c ? c + ROWS[((Math.floor(n / 100000) + (z % 2 === 0 ? 5 : 0)) % 20 + 20) % 20] : '';
  }
  const MGRS_RE = /^\s*(\d{1,2})\s*([C-HJ-NP-X])\s*([A-HJ-NP-Z])([A-HJ-NP-V])\s*(\d*)\s*(\d*)\s*$/i;
  function fromMGRS(ref) {
    const m = MGRS_RE.exec(ref); if (!m) return null;
    let [, z, band, col, row, a, b] = m; z = +z; band = band.toUpperCase(); col = col.toUpperCase(); row = row.toUpperCase();
    if (!b) { if (a.length % 2) return null; b = a.slice(a.length / 2); a = a.slice(0, a.length / 2); }
    if (a.length !== b.length || a.length > 5) return null;
    const ci = COLS[(z - 1) % 3].indexOf(col); if (ci < 0) return null;
    const scale = 10 ** (5 - a.length);
    const e = (ci + 1) * 100000 + (a ? +a * scale : 0);
    let n = (((ROWS.indexOf(row) - (z % 2 === 0 ? 5 : 0)) % 20 + 20) % 20) * 100000 + (b ? +b * scale : 0);
    const south = BANDS.indexOf(band) < BANDS.indexOf('N');
    const nMin = utmForward(cm(z), -80 + 8 * BANDS.indexOf(band), z, south).n;
    while (n < nMin - 100000) n += 2000000;
    return utmInverse(e, n, z, south);
  }
  /** "1.35, 103.82" | "48N 372000 149500" | MGRS → [lon, lat] or null. */
  function parseCoords(text) {
    let m = /^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/.exec(text);
    if (m) { const lat = +m[1], lon = +m[2]; return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lon, lat] : null; }
    m = /^\s*(\d{1,2})\s*([NS])\s+(\d+(?:\.\d+)?)\s*[mE]*\s+(\d+(?:\.\d+)?)\s*[mN]*\s*$/i.exec(text);
    if (m) return utmInverse(+m[3], +m[4], +m[1], m[2].toUpperCase() === 'S');
    return fromMGRS(text);
  }

  // Vincenty inverse on WGS84: distance (m) and initial bearing (° true). Falls back to a sphere
  // for nearly antipodal points, where the iteration doesn't converge.
  function inverse(lon1, lat1, lon2, lat2) {
    const b = A * (1 - F), L = rad(lon2 - lon1);
    const U1 = Math.atan((1 - F) * Math.tan(rad(lat1))), U2 = Math.atan((1 - F) * Math.tan(rad(lat2)));
    const sU1 = Math.sin(U1), cU1 = Math.cos(U1), sU2 = Math.sin(U2), cU2 = Math.cos(U2);
    let lam = L, sinS, cosS, sig, cos2a, cos2sm, it = 0, sinL, cosL;
    do {
      sinL = Math.sin(lam); cosL = Math.cos(lam);
      sinS = Math.hypot(cU2 * sinL, cU1 * sU2 - sU1 * cU2 * cosL);
      if (sinS === 0) return { m: 0, bearing: 0 };
      cosS = sU1 * sU2 + cU1 * cU2 * cosL; sig = Math.atan2(sinS, cosS);
      const sina = cU1 * cU2 * sinL / sinS; cos2a = 1 - sina * sina;
      cos2sm = cos2a ? cosS - 2 * sU1 * sU2 / cos2a : 0;
      const C = F / 16 * cos2a * (4 + F * (4 - 3 * cos2a));
      const prev = lam;
      lam = L + (1 - C) * F * sina * (sig + C * sinS * (cos2sm + C * cosS * (-1 + 2 * cos2sm * cos2sm)));
      if (Math.abs(lam - prev) < 1e-12) break;
    } while (++it < 200);
    if (it >= 200) {  // sphere fallback
      const d = 2 * 6371008.8 * Math.asin(Math.sqrt(Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(L / 2) ** 2));
      return { m: d, bearing: (deg(Math.atan2(Math.sin(L) * Math.cos(rad(lat2)), Math.cos(rad(lat1)) * Math.sin(rad(lat2)) - Math.sin(rad(lat1)) * Math.cos(rad(lat2)) * Math.cos(L))) + 360) % 360 };
    }
    const u2 = cos2a * (A * A - b * b) / (b * b);
    const AV = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)));
    const BV = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)));
    const dS = BV * sinS * (cos2sm + BV / 4 * (cosS * (-1 + 2 * cos2sm * cos2sm) - BV / 6 * cos2sm * (-3 + 4 * sinS * sinS) * (-3 + 4 * cos2sm * cos2sm)));
    return { m: b * AV * (sig - dS), bearing: (deg(Math.atan2(cU2 * sinL, cU1 * sU2 - sU1 * cU2 * cosL)) + 360) % 360 };
  }

  const dms = (v, pos, neg) => {
    // round to 0.1″ first, then split, so 59.97″ carries into the minute instead of showing 60.0″
    const t = Math.round(Math.abs(v) * 36000), d = Math.floor(t / 36000), m = Math.floor((t % 36000) / 600), s = (t % 600) / 10;
    return `${d}°${String(m).padStart(2, '0')}′${s.toFixed(1).padStart(4, '0')}″ ${v >= 0 ? pos : neg}`;
  };
  function format(lon, lat, kind) {
    if (kind === 'dms') return `${dms(lat, 'N', 'S')}  ${dms(lon, 'E', 'W')}`;
    if (kind === 'mgrs') return toMGRS(lon, lat, 5) || 'Outside MGRS (polar)';
    if (kind === 'utm') { const u = utmForward(lon, lat); return `${u.zone}${u.hemi} ${Math.round(u.e)}mE ${Math.round(u.n)}mN`; }
    return `${Math.abs(lat).toFixed(5)}° ${lat >= 0 ? 'N' : 'S'}  ${Math.abs(lon).toFixed(5)}° ${lon >= 0 ? 'E' : 'W'}`;
  }
  const fmtDist = m => m >= 10000 ? `${(m / 1000).toFixed(1)} km` : m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;

  const Geo = { zoneFor, bandFor, utmForward, utmInverse, toMGRS, fromMGRS, square, parseCoords, inverse, format, fmtDist, cm };
  if (typeof module !== 'undefined' && module.exports) module.exports = Geo; else root.Geo = Geo;
})(typeof window !== 'undefined' ? window : globalThis);
