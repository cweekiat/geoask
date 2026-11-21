"""Geospatial foundation models behind one interface, so GeoAsk isn't locked to any single model.

    from geoask.models import get, list_models
    enc = get("clay-v1.5")          # or "prithvi-eo-2.0", "dofa", "terramind", "galileo", ...
    emb = enc.embed_stack(stack)     # same call for every model

Third-party packages can add models through the ``geoask.models`` entry-point group.
"""

from .base import (
    BandRequirement,
    Embeddings,
    GeoEncoder,
    ModelInput,
    ModelNotInstalled,
    ModelSpec,
    SensorNotSupported,
)
from .registry import get, list_models, register

__all__ = [
    "BandRequirement", "Embeddings", "GeoEncoder", "ModelInput", "ModelNotInstalled",
    "ModelSpec", "SensorNotSupported", "get", "list_models", "register",
]
