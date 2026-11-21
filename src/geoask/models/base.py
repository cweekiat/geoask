"""The contract every geospatial foundation model (GFM) adapter implements.

Two kinds of model exist, and the contract covers both:

* **Wavelength-conditioned** (Clay, DOFA, Copernicus-FM, Panopticon): take any bands plus their
  wavelengths. ``bands="any"``.
* **Fixed-band** (Prithvi, SatMAE, TerraMind's per-modality tokenizers): need specific spectral bands.
  They declare ``BandRequirement``s by wavelength; GeoAsk maps each to the nearest band of whatever
  sensor is loaded, or refuses with ``SensorNotSupported``. Nothing is ever matched by band name.

Embeddings always carry the model id and version, so vectors from different models are never mixed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from ..data.grid import Grid
from ..data.load import Stack
from ..profiles import BandNotAvailable, InstrumentProfile

Modality = Literal["optical", "sar", "dem", "landcover"]


class ModelNotInstalled(RuntimeError):
    """The adapter exists but its weights/dependencies aren't installed yet."""


class SensorNotSupported(ValueError):
    """The loaded sensor lacks bands or modality the model needs."""


@dataclass(frozen=True)
class BandRequirement:
    """A band a fixed-band model needs, defined by wavelength (µm), not name."""

    name: str  # the model's own name for it, e.g. "B04" / "Red"
    center_um: float
    tolerance_um: float | None = None


@dataclass(frozen=True)
class ModelSpec:
    id: str  # e.g. "clay-v1.5"
    family: str  # e.g. "Clay"
    description: str
    modalities: tuple[Modality, ...]
    bands: Literal["any"] | tuple[BandRequirement, ...]
    chip_size: int  # input pixels per side
    patch_size: int | None = None  # ViT patch size (tokens per side = chip/patch)
    gsd_range_m: tuple[float, float] = (0.3, 100.0)  # pixel sizes it was trained around
    temporal_frames: int = 1  # >1 for models that take a time series
    embed_dim: int | None = None  # filled from the checkpoint when unknown
    license: str = "see model card"
    weights: str = ""  # where weights come from (HF repo id, URL)
    paper: str = ""
    integrated: bool = False  # True once the adapter actually runs

    @property
    def sensor_agnostic(self) -> bool:
        return self.bands == "any"


@dataclass
class ModelInput:
    """What a model receives: chips plus the metadata wavelength-conditioned models need."""

    pixels: np.ndarray  # (N, C, H, W) float32, physical units (reflectance / gamma0)
    wavelengths_um: np.ndarray  # (C,)
    gsd_m: float
    chip_bounds: list[tuple[float, float, float, float]]  # per chip, in grid CRS
    crs: str
    date: str
    valid_fraction: np.ndarray  # (N,) share of clear pixels in each chip
    band_names: list[str] = field(default_factory=list)


@dataclass
class Embeddings:
    """Model-tagged vectors, one per chip (and optionally a patch grid per chip)."""

    model_id: str
    model_version: str
    vectors: np.ndarray  # (N, D) float32, chip-level
    chip_bounds: list[tuple[float, float, float, float]]
    crs: str
    date: str
    valid_fraction: np.ndarray
    patches: np.ndarray | None = None  # (N, h, w, D) if the model gives patch tokens

    def cosine_to(self, other: Embeddings) -> np.ndarray:
        """Per-chip cosine distance to another date. Refuses to compare different models."""
        if (self.model_id, self.model_version) != (other.model_id, other.model_version):
            raise ValueError(
                f"can't compare {self.model_id}@{self.model_version} with "
                f"{other.model_id}@{other.model_version}"
            )
        a = self.vectors / (np.linalg.norm(self.vectors, axis=1, keepdims=True) + 1e-8)
        b = other.vectors / (np.linalg.norm(other.vectors, axis=1, keepdims=True) + 1e-8)
        return 1.0 - (a * b).sum(axis=1)


def chip_windows(grid: Grid, chip: int) -> list[tuple[int, int]]:
    """Top-left (row, col) of each full chip tiling the grid. Edges that don't fit are skipped."""
    return [(r, c) for r in range(0, grid.height - chip + 1, chip)
            for c in range(0, grid.width - chip + 1, chip)]


class GeoEncoder(ABC):
    """Base class for every GFM adapter. Subclasses set ``spec`` and implement ``_embed``."""

    spec: ModelSpec
    version: str = "unloaded"

    # ---- sensor compatibility ---------------------------------------------------------
    def select_bands(self, profile: InstrumentProfile) -> list[str]:
        """Return the stack keys to load for this model, mapped by wavelength."""
        if profile.modality not in self.spec.modalities:
            raise SensorNotSupported(f"{self.spec.id} doesn't take {profile.modality} input")
        if profile.modality == "sar":
            return [b.polarization.lower() for b in profile.bands if b.polarization]
        if self.spec.bands == "any":
            return [b.name for b in profile.bands]
        out = []
        for req in self.spec.bands:
            try:
                out.append(profile.band_near(req.center_um, req.tolerance_um).name)
            except BandNotAvailable as e:
                raise SensorNotSupported(f"{self.spec.id} needs {req.name}: {e}") from e
        return out

    def supports(self, profile: InstrumentProfile) -> bool:
        try:
            self.select_bands(profile)
            return True
        except SensorNotSupported:
            return False

    # ---- input preparation (shared) -----------------------------------------------------
    def prepare(self, stack: Stack, band_keys: list[str], wavelengths_um: list[float]) -> ModelInput:
        chip = self.spec.chip_size
        wins = chip_windows(stack.grid, chip)
        if not wins:
            raise ValueError(f"area is smaller than one {chip}×{chip} chip at {stack.grid.res} m")
        cube = np.stack([stack.bands[k] for k in band_keys])  # (C, H, W)
        t = stack.grid.transform
        pixels, bounds, valid = [], [], []
        for r, c in wins:
            px = cube[:, r:r + chip, c:c + chip]
            pixels.append(np.nan_to_num(px, nan=0.0))
            valid.append(float(stack.valid[r:r + chip, c:c + chip].mean()))
            x0, y0 = t @ (c, r)
            x1, y1 = t @ (c + chip, r + chip)
            bounds.append((x0, y1, x1, y0))
        return ModelInput(
            pixels=np.stack(pixels).astype(np.float32),
            wavelengths_um=np.asarray(wavelengths_um, np.float32),
            gsd_m=stack.grid.res,
            chip_bounds=bounds,
            crs=stack.grid.crs,
            date=stack.date,
            valid_fraction=np.asarray(valid, np.float32),
            band_names=band_keys,
        )

    # ---- model -------------------------------------------------------------------------
    def load(self, device: str = "auto") -> None:
        """Load weights. Adapters that need weights override this."""

    @abstractmethod
    def _embed(self, inputs: ModelInput) -> tuple[np.ndarray, np.ndarray | None]:
        """Return (chip vectors (N, D), optional patch tokens (N, h, w, D))."""

    def embed(self, inputs: ModelInput) -> Embeddings:
        vec, patches = self._embed(inputs)
        return Embeddings(self.spec.id, self.version, vec.astype(np.float32), inputs.chip_bounds,
                          inputs.crs, inputs.date, inputs.valid_fraction, patches)

    def embed_stack(self, stack: Stack, profile: InstrumentProfile) -> Embeddings:
        keys = self.select_bands(profile)
        wl = []
        for k in keys:
            b = (profile.polarization(k) if profile.modality == "sar"
                 else next(b for b in profile.bands if b.name == k))
            wl.append(b.center_um)
        return self.embed(self.prepare(stack, keys, wl))
