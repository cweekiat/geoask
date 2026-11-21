"""Adapters for well-known geospatial foundation models.

Each one declares its spec now (inputs, bands by wavelength, chip/patch size, licence, weights), so
the rest of GeoAsk — sensor checks, the model picker, embedding storage — already works with it.
``_embed`` gets implemented model by model (Clay first; see docs/PLAN.md §6).

Spec values come from each model's paper/model card; ``embed_dim`` stays None until read from the
checkpoint, rather than guessed. Weight and paper links are filled in (and checked) when each
adapter is integrated.
"""

from __future__ import annotations

from ..base import BandRequirement, GeoEncoder, ModelInput, ModelNotInstalled, ModelSpec
from ..registry import register


class _Planned(GeoEncoder):
    install_hint = ""

    def load(self, device: str = "auto") -> None:
        raise ModelNotInstalled(f"{self.spec.id} adapter is planned, not integrated yet. "
                                f"{self.install_hint}")

    def _embed(self, inputs: ModelInput):
        self.load()


# HLS (Harmonized Landsat Sentinel-2) bands used by Prithvi, by wavelength.
_HLS6 = (
    BandRequirement("Blue", 0.490), BandRequirement("Green", 0.560),
    BandRequirement("Red", 0.665), BandRequirement("NIR_Narrow", 0.865),
    BandRequirement("SWIR1", 1.610), BandRequirement("SWIR2", 2.190),
)


@register
class Prithvi(_Planned):
    spec = ModelSpec(
        id="prithvi-eo-2.0", family="Prithvi",
        description="NASA/IBM ViT trained on HLS time series (6 bands, 30 m). Fixed bands.",
        modalities=("optical",), bands=_HLS6, chip_size=224, patch_size=16,
        gsd_range_m=(10, 60), temporal_frames=4,
        license="Apache-2.0", weights="ibm-nasa-geospatial/Prithvi-EO-2.0-300M",
    )


@register
class DOFA(_Planned):
    spec = ModelSpec(
        id="dofa", family="DOFA",
        description="Dynamic One-For-All: wavelength-conditioned hypernetwork patch embedding; "
                    "optical, SAR and hyperspectral.",
        modalities=("optical", "sar"), bands="any", chip_size=224, patch_size=16,
    )


@register
class TerraMind(_Planned):
    spec = ModelSpec(
        id="terramind-1.0", family="TerraMind",
        description="IBM/ESA any-to-any generative model over S1, S2, DEM, land cover and NDVI. "
                    "Can generate optical views from SAR to fill cloud gaps.",
        modalities=("optical", "sar", "dem", "landcover"), bands="any",
        chip_size=224, patch_size=16, license="Apache-2.0",
        weights="ibm-esa-geospatial/TerraMind-1.0-base",
    )


@register
class Galileo(_Planned):
    spec = ModelSpec(
        id="galileo", family="Galileo",
        description="Multimodal, multi-scale pretrained model with nano/tiny sizes — candidate "
                    "for the iPhone.",
        modalities=("optical", "sar", "dem"), bands="any", chip_size=96,
        temporal_frames=12,
    )


@register
class CopernicusFM(_Planned):
    spec = ModelSpec(
        id="copernicus-fm", family="Copernicus-FM",
        description="Extends dynamic hypernetworks with wavelength and bandwidth (and metadata) "
                    "to any Copernicus sensor.",
        modalities=("optical", "sar"), bands="any", chip_size=224, patch_size=16,
    )
