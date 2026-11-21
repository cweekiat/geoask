"""Local photo handling: read metadata, then re-encode without it.

Nothing here touches the network. The agent never receives the original file: it gets a JPEG
re-encoded from the pixels (so EXIF/XMP/GPS can't leak) and, separately, only the metadata facts
the user chose to share.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from PIL import ExifTags, Image, ImageOps

MAX_SIDE = 1568  # Claude's useful image size; larger only costs tokens
MAX_BYTES = 20 * 1024 * 1024
MAX_PHOTOS = 5


@dataclass
class Photo:
    index: int
    name: str
    jpeg_b64: str  # re-encoded, metadata-free
    width: int
    height: int
    meta: dict = field(default_factory=dict)  # facts read locally (may include GPS)
    thumb_b64: str = ""  # small preview for the UI

    def block(self) -> dict:
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                            "data": self.jpeg_b64}}


def _ratio(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        num, den = v
        return num / den if den else 0.0


def _dms(vals, ref) -> float | None:
    try:
        d, m, s = (_ratio(x) for x in vals)
    except (TypeError, ValueError):
        return None
    out = d + m / 60 + s / 3600
    return -out if str(ref).upper() in ("S", "W") else out


def read_metadata(img: Image.Image) -> dict:
    """EXIF facts useful for locating: GPS, capture time (with UTC offset when recorded), camera,
    compass heading and focal length. Missing fields are simply absent."""
    meta: dict = {}
    exif = img.getexif()
    if not exif:
        return meta
    tags = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
    try:
        sub = exif.get_ifd(ExifTags.IFD.Exif)
        tags.update({ExifTags.TAGS.get(k, k): v for k, v in sub.items()})
    except (KeyError, AttributeError):
        pass
    cam = " ".join(str(tags[k]).strip("\x00 ") for k in ("Make", "Model") if tags.get(k))
    if cam:
        meta["camera"] = cam
    when = tags.get("DateTimeOriginal") or tags.get("DateTime")
    if when:
        meta["local_time"] = str(when).strip("\x00 ")
        off = tags.get("OffsetTimeOriginal") or tags.get("OffsetTime")
        if off:
            meta["utc_offset"] = str(off).strip("\x00 ")
            try:
                t = datetime.strptime(meta["local_time"], "%Y:%m:%d %H:%M:%S")
                sign = -1 if meta["utc_offset"].startswith("-") else 1
                hh, mm = meta["utc_offset"].lstrip("+-").split(":")
                tz = timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))
                meta["utc_time"] = t.replace(tzinfo=tz).astimezone(timezone.utc).isoformat()
            except (ValueError, IndexError):
                pass
    if tags.get("FocalLengthIn35mmFilm"):
        meta["focal_35mm"] = int(_ratio(tags["FocalLengthIn35mmFilm"]))
    try:
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    except (KeyError, AttributeError):
        gps = {}
    if gps:
        g = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
        lat = _dms(g.get("GPSLatitude"), g.get("GPSLatitudeRef")) if g.get("GPSLatitude") else None
        lon = _dms(g.get("GPSLongitude"), g.get("GPSLongitudeRef")) if g.get("GPSLongitude") else None
        if lat is not None and lon is not None and (lat, lon) != (0.0, 0.0):
            meta["gps"] = {"lat": round(lat, 6), "lon": round(lon, 6)}
            if g.get("GPSAltitude") is not None:
                meta["gps"]["altitude_m"] = round(_ratio(g["GPSAltitude"]), 1)
            if g.get("GPSImgDirection") is not None:
                meta["gps"]["heading_deg"] = round(_ratio(g["GPSImgDirection"]), 1)
    return meta


def load(data: bytes, index: int, name: str = "") -> Photo:
    if len(data) > MAX_BYTES:
        raise ValueError(f"{name or 'Photo'} is larger than 20 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise ValueError(f"{name or 'That file'} isn't an image GeoAsk can read.") from e
    meta = read_metadata(img)
    img = ImageOps.exif_transpose(img).convert("RGB")  # apply rotation, then drop metadata
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)  # a fresh JPEG carries no EXIF/XMP/GPS
    th = img.copy()
    th.thumbnail((256, 256))
    tb = io.BytesIO()
    th.save(tb, "JPEG", quality=80)
    return Photo(index, name, base64.standard_b64encode(buf.getvalue()).decode(), img.width,
                 img.height, meta, base64.standard_b64encode(tb.getvalue()).decode())
