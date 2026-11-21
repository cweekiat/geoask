"""Instrument profiles. Everything downstream looks bands up by wavelength, never by band name.

A profile can be loaded from YAML (``profiles/``), or derived from a STAC item's ``eo:bands`` /
``raster:bands`` metadata. Derived values (such as per-item scale/offset) override YAML defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

# Common spectral targets (micrometres). Tools ask for these, not for band names.
WAVELENGTHS = {
    "blue": 0.490,
    "green": 0.560,
    "red": 0.665,
    "rededge": 0.705,
    "nir": 0.842,
    "swir1": 1.610,
    "swir2": 2.190,
}


class BandNotAvailable(LookupError):
    """The sensor has no band close enough to the requested wavelength."""


@dataclass(frozen=True)
class Band:
    name: str
    asset: str
    center_um: float
    width_um: float | None = None
    gsd_m: float | None = None
    scale: float = 1.0
    offset: float = 0.0
    polarization: str | None = None


@dataclass(frozen=True)
class CloudMask:
    asset: str
    invalid: tuple[int, ...]


@dataclass(frozen=True)
class InstrumentProfile:
    id: str
    modality: str  # "optical" | "sar"
    bands: tuple[Band, ...]
    gsd_m: float
    nodata: float | None = None
    platform: str | None = None
    stac: dict[str, Any] = field(default_factory=dict)
    cloud_mask: CloudMask | None = None

    # ---- lookup -------------------------------------------------------------------------
    def band_near(self, target_um: float | str, tolerance: float | None = None) -> Band:
        """Return the band whose centre is closest to ``target_um`` (or a named target).

        Tolerance defaults to the larger of 0.06 µm and 8% of the target, so red (0.665) can't
        silently match red-edge (0.705+) on a sensor that lacks red.
        """
        if self.modality != "optical":
            raise BandNotAvailable(f"{self.id} is {self.modality}; no spectral bands")
        if isinstance(target_um, str):
            target_um = WAVELENGTHS[target_um]
        tol = tolerance if tolerance is not None else max(0.06, 0.08 * target_um)
        best = min(self.bands, key=lambda b: abs(b.center_um - target_um))
        if abs(best.center_um - target_um) > tol:
            raise BandNotAvailable(
                f"{self.id}: no band within {tol:.3f} µm of {target_um:.3f} µm "
                f"(closest {best.name} at {best.center_um:.3f})"
            )
        return best

    def has(self, target_um: float | str) -> bool:
        try:
            self.band_near(target_um)
            return True
        except BandNotAvailable:
            return False

    def polarization(self, pol: str) -> Band:
        for b in self.bands:
            if (b.polarization or "").upper() == pol.upper():
                return b
        raise BandNotAvailable(f"{self.id}: no {pol} polarisation")

    # ---- derivation ---------------------------------------------------------------------
    def with_item(self, item: Any) -> InstrumentProfile:
        """Override per-band scale/offset from a STAC item's ``raster:bands`` metadata."""
        assets = item.assets if hasattr(item, "assets") else item["assets"]
        props = item.properties if hasattr(item, "properties") else item.get("properties", {})
        # Some catalogues bake the offset into the pixels but still advertise it in raster:bands
        # (Earth Search sets earthsearch:boa_offset_applied). Applying it again darkens the image.
        flag = self.stac.get("offset_applied_property")
        baked = bool(flag and props.get(flag))
        bands = []
        for b in self.bands:
            a = assets.get(b.asset)
            extra = (a.extra_fields if hasattr(a, "extra_fields") else a) if a is not None else {}
            rb = (extra.get("raster:bands") or [{}])[0]
            bands.append(
                replace(
                    b,
                    scale=rb.get("scale", b.scale),
                    offset=0.0 if baked else rb.get("offset", b.offset),
                )
            )
        return replace(self, bands=tuple(bands))


def _from_dict(d: dict[str, Any]) -> InstrumentProfile:
    scale = d.get("default_scale", 1.0)
    offset = d.get("default_offset", 0.0)
    bands = tuple(
        Band(
            name=b["name"],
            asset=b.get("asset", b["name"]),
            center_um=float(b["center_um"]),
            width_um=b.get("width_um"),
            gsd_m=b.get("gsd_m", d.get("gsd_m")),
            scale=b.get("scale", scale),
            offset=b.get("offset", offset),
            polarization=b.get("polarization"),
        )
        for b in d["bands"]
    )
    cm = d.get("cloud_mask")
    return InstrumentProfile(
        id=d["id"],
        modality=d["modality"],
        bands=bands,
        gsd_m=float(d["gsd_m"]),
        nodata=d.get("nodata"),
        platform=d.get("platform"),
        stac=d.get("stac", {}),
        cloud_mask=CloudMask(cm["asset"], tuple(cm["invalid"])) if cm else None,
    )


def load_profile(name_or_path: str | Path) -> InstrumentProfile:
    """Load a profile by id (bundled) or by path to a YAML file."""
    p = Path(name_or_path)
    if p.suffix in (".yaml", ".yml") and p.exists():
        return _from_dict(yaml.safe_load(p.read_text()))
    for base in (Path(__file__).resolve().parents[2] / "profiles",):
        cand = base / f"{name_or_path}.yaml"
        if cand.exists():
            return _from_dict(yaml.safe_load(cand.read_text()))
    try:  # installed wheel
        txt = resources.files("geoask").joinpath(f"_profiles/{name_or_path}.yaml").read_text()
        return _from_dict(yaml.safe_load(txt))
    except (FileNotFoundError, ModuleNotFoundError) as e:
        raise FileNotFoundError(f"no instrument profile named {name_or_path!r}") from e


def profile_from_stac_item(item: Any, profile_id: str | None = None) -> InstrumentProfile:
    """Derive a profile from any STAC item with ``eo:bands`` (optical) or ``sar:*`` metadata.

    This is how GeoAsk handles a sensor it has never seen before.
    """
    d = item.to_dict() if hasattr(item, "to_dict") else item
    props = d.get("properties", {})
    bands: list[Band] = []
    sar = any(k.startswith("sar:") for k in props)
    for key, a in d.get("assets", {}).items():
        rb = (a.get("raster:bands") or [{}])[0]
        gsd = a.get("gsd", props.get("gsd"))
        for eb in a.get("eo:bands", []) or []:
            if eb.get("center_wavelength"):
                bands.append(
                    Band(
                        name=eb.get("name", key),
                        asset=key,
                        center_um=float(eb["center_wavelength"]),
                        width_um=eb.get("full_width_half_max"),
                        gsd_m=gsd,
                        scale=rb.get("scale", 1.0),
                        offset=rb.get("offset", 0.0),
                    )
                )
        if sar and key.lower() in ("vv", "vh", "hh", "hv"):
            bands.append(
                Band(name=key, asset=key, center_um=55465.76, gsd_m=gsd, polarization=key.upper())
            )
    if not bands:
        raise ValueError("STAC item has no eo:bands with center_wavelength and no SAR assets")
    gsds = [b.gsd_m for b in bands if b.gsd_m]
    return InstrumentProfile(
        id=profile_id or d.get("collection") or "unknown",
        modality="sar" if sar else "optical",
        bands=tuple(bands),
        gsd_m=float(min(gsds)) if gsds else float(props.get("gsd", 10)),
        platform=props.get("platform"),
    )
