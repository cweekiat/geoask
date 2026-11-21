"""Clay v1.5 adapter: GeoAsk's sensor-agnostic inputs → Clay's conventions.

Clay's own conventions, which this adapter translates so the rest of GeoAsk never sees them:

* **Normalisation** per platform from Clay's metadata (Sentinel-2 in DN = reflectance × 10 000;
  Sentinel-1 in dB). A sensor Clay never saw is normalised with per-scene band statistics.
* **Band wavelengths** go straight into the dynamic patch embedding. For SAR, Clay uses
  placeholder "wavelengths" (VV 3.5, VH 4.0), not physical ones, so they're taken from its metadata.
* **Time** = sin/cos of ISO week and hour; **location** = sin/cos of latitude and longitude.

PyTorch is imported lazily, so ``geoask`` works without it until Clay is actually used.
"""

from __future__ import annotations

import math
import os
from functools import cache
from pathlib import Path

import numpy as np
import yaml
from rasterio.warp import transform as warp_transform

from ...profiles import InstrumentProfile
from ..base import GeoEncoder, ModelInput, ModelNotInstalled, ModelSpec, SensorNotSupported
from ..registry import register

WEIGHTS = Path(os.environ.get("GEOASK_MODELS", Path.home() / ".cache" / "geoask" / "models")) \
    / "clay-v1.5-encoder.pt"
UNIT = {"sentinel-2-l2a": "dn10000", "sentinel-1-rtc": "db"}  # how Clay's stats are expressed
MAX_OPTICAL_GSD_FACTOR = 2.0  # skip bands much coarser than the sensor (e.g. S2 60 m bands)


@cache
def clay_metadata() -> dict:
    return yaml.safe_load((Path(__file__).parent / "clay_metadata.yaml").read_text())


@register
class Clay(GeoEncoder):
    spec = ModelSpec(
        id="clay-v1.5", family="Clay",
        description="MAE-pretrained ViT-L with a wavelength-conditioned patch embedding. Takes "
                    "any bands plus pixel size, time and location.",
        modalities=("optical", "sar"), bands="any", chip_size=256, patch_size=8,
        embed_dim=1024, license="Apache-2.0",
        weights="made-with-clay/Clay (v1.5/clay-v1.5.ckpt; encoder extracted by "
                "scripts/fetch_clay.py)",
        paper="https://clay-foundation.github.io/model/",
        integrated=True,
    )
    version = "v1.5"

    def __init__(self) -> None:
        self._model = None
        self._torch = None
        self.device = "cpu"
        self.batch = int(os.environ.get("GEOASK_CLAY_BATCH", "4"))

    # ---- bands ----------------------------------------------------------------------------
    def select_bands(self, profile: InstrumentProfile) -> list[str]:
        if profile.modality not in self.spec.modalities:
            raise SensorNotSupported(f"clay-v1.5 doesn't take {profile.modality} input")
        if profile.modality == "sar":
            return [b.name for b in profile.bands if b.polarization]
        meta = clay_metadata().get(profile.id)
        if meta:  # use the exact band set Clay was trained with for this platform
            wl = meta["bands"]["wavelength"]
            return [profile.band_near(wl[b], 0.02).name for b in meta["band_order"]]
        return [b.name for b in profile.bands
                if (b.gsd_m or profile.gsd_m) <= profile.gsd_m * MAX_OPTICAL_GSD_FACTOR]

    def _waves_and_stats(self, sensor: str, names: list[str], phys_um: np.ndarray):
        meta = clay_metadata().get(sensor)
        if meta and all(n in meta["bands"]["mean"] for n in names):
            b = meta["bands"]
            waves = np.array([b["wavelength"][n] for n in names], np.float32)
            mean = np.array([b["mean"][n] for n in names], np.float32)
            std = np.array([b["std"][n] for n in names], np.float32)
            return waves, mean, std, UNIT.get(sensor, "native")
        return phys_um.astype(np.float32), None, None, "scene"

    # ---- model ----------------------------------------------------------------------------
    def load(self, device: str = "auto") -> None:
        if self._model is not None:
            return
        try:
            import torch
        except ImportError as e:
            raise ModelNotInstalled("clay-v1.5 needs PyTorch: pip install 'geoask[ml]'") from e
        if not WEIGHTS.exists():
            raise ModelNotInstalled(f"Clay weights not found at {WEIGHTS}. "
                                    "Run: python scripts/fetch_clay.py")
        from .clay_net import ClayEncoder

        if device == "auto":
            device = ("mps" if torch.backends.mps.is_available()
                      else "cuda" if torch.cuda.is_available() else "cpu")
        sd = torch.load(WEIGHTS, map_location="cpu", weights_only=True)["state_dict"]
        model = ClayEncoder()
        model.load_state_dict({k: v.float() for k, v in sd.items()}, strict=True)
        self._model = model.eval().to(device)
        self._torch, self.device = torch, device

    def _embed(self, inputs: ModelInput):
        self.load()
        torch = self._torch
        px = inputs.pixels.astype(np.float32)  # (N, C, H, W), NaN = missing
        waves, mean, std, unit = self._waves_and_stats(inputs.sensor, inputs.band_names,
                                                       inputs.wavelengths_um)
        if unit == "dn10000":
            px = px * 10000.0
        elif unit == "db":
            px = 10 * np.log10(np.clip(px, 1e-6, None))
        if mean is None:  # unseen sensor: per-scene statistics
            mean = np.nanmean(px, axis=(0, 2, 3))
            std = np.nanstd(px, axis=(0, 2, 3)) + 1e-6
        px = (px - mean[None, :, None, None]) / std[None, :, None, None]
        px = np.nan_to_num(px, nan=0.0)  # missing → the band mean

        when = inputs.acquired
        week = (when.isocalendar().week if when else 26) * 2 * math.pi / 52
        hour = (when.hour if when else 12) * 2 * math.pi / 24
        time = np.array([math.sin(week), math.cos(week), math.sin(hour), math.cos(hour)],
                        np.float32)
        cx = [(b[0] + b[2]) / 2 for b in inputs.chip_bounds]
        cy = [(b[1] + b[3]) / 2 for b in inputs.chip_bounds]
        lons, lats = warp_transform(inputs.crs, "EPSG:4326", cx, cy)
        latlon = np.array([[math.sin(math.radians(la)), math.cos(math.radians(la)),
                            math.sin(math.radians(lo)), math.cos(math.radians(lo))]
                           for lo, la in zip(lons, lats)], np.float32)

        dev = self.device
        waves_t = torch.from_numpy(waves).to(dev)
        gsd_t = torch.tensor([inputs.gsd_m], dtype=torch.float32)
        cls_out, patch_out = [], []
        with torch.inference_mode():
            for i in range(0, len(px), self.batch):
                sl = slice(i, i + self.batch)
                n = len(px[sl])
                cls, patches = self._model(
                    torch.from_numpy(px[sl]).to(dev),
                    torch.from_numpy(np.repeat(time[None], n, 0)).to(dev),
                    torch.from_numpy(latlon[sl]).to(dev),
                    gsd_t, waves_t)
                cls_out.append(cls.float().cpu().numpy())
                patch_out.append(patches.to(torch.float16).cpu().numpy())
        return np.concatenate(cls_out), np.concatenate(patch_out)
