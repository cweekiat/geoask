# GeoAsk

**Ask questions about Singapore in plain language and get answers computed from satellite imagery.**
It works with any satellite sensor, uses imagery at about 10 m or sharper, runs locally, and needs
no API keys.

> *"How much vegetation did Tengah lose between 2019 and 2025?"*
> → **N ha** of NDVI loss, a before/after pair, a change map, and the exact Sentinel-2 scenes used.

GeoAsk streams just the pixels for your area from open data buckets (Cloud-Optimized GeoTIFFs over
HTTPS range requests). It looks bands up **by wavelength, not by name**, so the same tools work on
any sensor with the right bands. The language model only chooses which tools to run; every number
comes from deterministic code on native-resolution pixels.

Status: **v0.1, early build.** See [docs/PLAN.md](docs/PLAN.md) for the full plan.

## Quick start (Linux or macOS)

```bash
git clone https://github.com/cweekiat/geoask && cd geoask
uv venv && uv pip install -e .
geoask scenes --place tengah --start 2025-01-01 --end 2025-11-30
geoask change --place tengah --index ndvi --t0 2019-01-01/2019-12-31 --t1 2025-01-01/2025-11-30
```

Outputs (PNG quicklooks, a GeoTIFF change layer and `result.json`) go to `out/`. A read cache in
`~/.cache/geoask` is capped at 500 MB (`GEOASK_CACHE_MB`). Raw scenes are never stored.

## Design

| | |
|---|---|
| **Works with any sensor** | Instrument profiles (`profiles/*.yaml`, or generated from STAC metadata) describe the bands by wavelength. |
| **No keys** | Public STAC catalogues plus COGs on AWS open data and Planetary Computer (anonymous token). |
| **Trustworthy numbers** | The language model plans; deterministic tools compute; answers cite their scenes and the clear-pixel percentage. |
| **Foundation models** *(planned)* | Clay v1.5 embeddings for change detection, similarity search and few-shot classification. |
| **Super-resolution** *(planned)* | 2.5 m view with a consistency-checked confidence map. Display only; never used for measurements. |
| **Platforms** | `geoask-py` on Linux and macOS; a native iPhone and Mac app optimised for Apple silicon (Core ML, Foundation Models). |

## Data and attribution

Contains modified Copernicus Sentinel data, processed by GeoAsk. Sentinel-2 L2A via Element84 Earth
Search (AWS Open Data); Sentinel-1 RTC via Microsoft Planetary Computer. Place boundaries are
currently approximate bounding boxes.

## License

MIT
