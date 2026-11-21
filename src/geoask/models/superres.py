"""Super-resolution, for display only. Never used for measurement.

A small interface so any SR model can plug in (the same idea as the GFM registry):

    sr = get_super_resolver("sen2sr-lite")
    out = sr.predict(rgbn)          # (4, H, W) reflectance 0–1 → (4, 4H, 4W)

``sen2sr-lite``: SEN2SR-Lite RGBN ×4 (10 m → 2.5 m), CC0-1.0, 3.4 MB of weights fetched by
``geoask fetch sen2sr`` (or ``scripts/fetch_sen2sr.py``), pinned by commit and SHA-256.
"""

from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np

from .base import ModelNotInstalled

MODELS_DIR = Path.home() / ".cache" / "geoask" / "models"
REPO = "WEO-SAS/sen2sr"
REVISION = "743c1ba850b90b92b1288afa25701fe3d00f2cf7"
FILES = {  # name → sha256 (LFS oid)
    "model.safetensor": "479aa796d5068d0b1206118ccbca27bd3223df0214db1a9b31a1e18349ed1c7e",
    "hard_constraint.safetensor": "fbad981519066387c413ead1d6af7ef3e0d2947c34147ba90163fc79ae539239",
}


@dataclass(frozen=True)
class SRSpec:
    id: str
    scale: int
    bands: tuple[str, ...]  # wavelength names, in the model's input order
    gsd_in_m: float
    licence: str
    citation: str


SEN2SR_LITE = SRSpec("sen2sr-lite", 4, ("red", "green", "blue", "nir"), 10.0, "CC0-1.0",
                     "Aybar et al., SEN2SR (ESA OpenSR); SPAN backbone (Wan et al. 2024)")


def fetch_sen2sr(dest: Path = MODELS_DIR / "sen2sr-lite") -> Path:
    """Download the two weight files (3.4 MB) at the pinned revision and verify them."""
    dest.mkdir(parents=True, exist_ok=True)
    for name, sha in FILES.items():
        path = dest / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == sha:
            continue
        url = f"https://huggingface.co/{REPO}/resolve/{REVISION}/{name}"
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError(f"{name}: checksum mismatch, not saved")
        path.write_bytes(data)
    return dest


class Sen2SRLite:
    spec = SEN2SR_LITE
    PATCH, OVERLAP = 128, 32  # the constraint mask is sized for 128 px input tiles

    def __init__(self, weights_dir: Path = MODELS_DIR / "sen2sr-lite", device: str | None = None):
        files = [weights_dir / f for f in FILES]
        if not all(f.exists() for f in files):
            raise ModelNotInstalled(
                "The super-resolution model isn't installed. Run `geoask fetch sen2sr` "
                "(3.4 MB, CC0).")
        import torch

        from .adapters.sen2sr_net import CNNSR, HardConstraint, load_safetensors

        self.torch = torch
        self.device = device or ("mps" if torch.backends.mps.is_available() else
                                 "cuda" if torch.cuda.is_available() else "cpu")
        net = CNNSR(4, 4, 24, 4, 6)
        net.load_state_dict(load_safetensors(files[0]), strict=False)
        missing = {k for k in net.state_dict() if k not in load_safetensors(files[0])}
        if missing:
            raise RuntimeError(f"SEN2SR weights are missing {sorted(missing)[:3]}…")
        self.net = net.eval()
        self.hc = HardConstraint(load_safetensors(files[1])["weights"]).eval()
        for m in self.net.modules():
            if hasattr(m, "fuse"):
                m.fuse()

    def _run(self, tiles: np.ndarray) -> np.ndarray:
        torch = self.torch
        x = torch.from_numpy(tiles)
        with torch.no_grad():
            try:
                net, hc = self.net.to(self.device), self.hc.to(self.device)
                xd = x.to(self.device)
                out = hc(xd, torch.clamp(net(xd), min=0)).cpu()
            except (RuntimeError, NotImplementedError):  # e.g. an FFT op missing on MPS
                net, hc = self.net.to("cpu"), self.hc.to("cpu")
                out = hc(x, torch.clamp(net(x), min=0))
        return out.numpy()

    def predict(self, rgbn: np.ndarray, batch: int = 8) -> np.ndarray:
        """(4, H, W) reflectance (0–1, NaN allowed) → (4, 4H, 4W). Overlapping 128 px tiles,
        blended with a smooth window so tile seams don't show."""
        c, h, w = rgbn.shape
        s, p, ov = self.spec.scale, self.PATCH, self.OVERLAP
        step = p - ov
        img = np.nan_to_num(rgbn, nan=0.0).astype(np.float32).clip(0, 1)
        ph, pw = max(p, -(-(h - p) // step) * step + p), max(p, -(-(w - p) // step) * step + p)
        img = np.pad(img, ((0, 0), (0, ph - h), (0, pw - w)), mode="reflect" if min(h, w) > 1 else "edge")
        out = np.zeros((c, ph * s, pw * s), np.float32)
        wsum = np.zeros((ph * s, pw * s), np.float32)
        ramp = np.minimum(np.arange(p * s) + 1, np.arange(p * s)[::-1] + 1).astype(np.float32)
        win = np.outer(np.minimum(ramp, ov * s), np.minimum(ramp, ov * s))
        origins = [(y, x) for y in range(0, ph - p + 1, step) for x in range(0, pw - p + 1, step)]
        for i in range(0, len(origins), batch):
            chunk = origins[i:i + batch]
            tiles = np.stack([img[:, y:y + p, x:x + p] for y, x in chunk])
            for (y, x), t in zip(chunk, self._run(tiles)):
                out[:, y * s:(y + p) * s, x * s:(x + p) * s] += t * win
                wsum[y * s:(y + p) * s, x * s:(x + p) * s] += win
        return (out / np.maximum(wsum, 1e-6))[:, : h * s, : w * s]


def consistency(lr: np.ndarray, sr: np.ndarray, scale: int) -> np.ndarray:
    """Per 10 m pixel: mean |SR averaged back to 10 m − original| over the bands. Near 0 means the
    added detail is consistent with what the satellite measured."""
    c, h, w = lr.shape
    back = sr[:, : h * scale, : w * scale].reshape(c, h, scale, w, scale).mean(axis=(2, 4))
    return np.nanmean(np.abs(back - lr), axis=0)


@cache
def get_super_resolver(model_id: str = "sen2sr-lite") -> Sen2SRLite:
    if model_id != "sen2sr-lite":
        raise KeyError(f"unknown super-resolution model {model_id!r}")
    return Sen2SRLite()
