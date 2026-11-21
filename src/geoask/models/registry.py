"""Model registry: built-in adapters plus any installed via the ``geoask.models`` entry points."""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import entry_points

from .base import GeoEncoder, ModelSpec

_REGISTRY: dict[str, Callable[[], GeoEncoder]] = {}
_loaded_plugins = False


def register(factory: type[GeoEncoder] | Callable[[], GeoEncoder]):
    """Class decorator (or call) that makes an adapter available by its ``spec.id``."""
    spec: ModelSpec = factory.spec  # type: ignore[attr-defined]
    _REGISTRY[spec.id] = factory
    return factory


def _ensure_loaded() -> None:
    global _loaded_plugins
    from . import adapters  # noqa: F401  (registers built-ins)

    if not _loaded_plugins:
        _loaded_plugins = True
        for ep in entry_points(group="geoask.models"):
            register(ep.load())


def list_models() -> list[ModelSpec]:
    _ensure_loaded()
    return [f.spec for f in _REGISTRY.values()]  # type: ignore[attr-defined]


_INSTANCES: dict[str, GeoEncoder] = {}


def get(model_id: str, fresh: bool = False) -> GeoEncoder:
    """Return the adapter for ``model_id``. Instances are shared so weights load once per process."""
    _ensure_loaded()
    if model_id not in _REGISTRY:
        raise KeyError(f"unknown model {model_id!r}; available: {', '.join(sorted(_REGISTRY))}")
    if fresh:
        return _REGISTRY[model_id]()
    if model_id not in _INSTANCES:
        _INSTANCES[model_id] = _REGISTRY[model_id]()
    return _INSTANCES[model_id]
