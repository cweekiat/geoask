# GeoAsk

**Ask questions about any place on Earth in plain language and get answers computed from satellite imagery.**
It works with any satellite sensor, uses imagery at about 10 m or sharper, runs locally, and needs
no API keys.

> *"How much vegetation did Tengah lose between 2019 and 2025?"*
> → **N ha** of NDVI loss, a before/after pair, a change map, and the exact Sentinel-2 scenes used.

GeoAsk streams just the pixels for your area from open data buckets (Cloud-Optimized GeoTIFFs over
HTTPS range requests). It looks bands up **by wavelength, not by name**, so the same tools work on
any sensor with the right bands. The language model only chooses which tools to run; every number
comes from deterministic code on native-resolution pixels.

Status: **v0.4: free-form questions about any place or a drawn area.** See [docs/PLAN.md](docs/PLAN.md) for the full plan and
[docs/DESIGN.md](docs/DESIGN.md) for the app's design and HIG review.

**[Try the Investigator demo →](https://cweekiat.github.io/geoask/app/)** It runs in Demo mode on
GitHub Pages (a precomputed answer). Run it locally for live analysis.

## Quick start (Linux or macOS)

```bash
git clone https://github.com/cweekiat/geoask && cd geoask
uv venv && uv pip install -e .
geoask scenes --place tengah --start 2025-01-01 --end 2025-11-30
geoask change --place tengah --index ndvi --t0 2019-01-01/2019-12-31 --t1 2025-01-01/2025-11-30
```

Run the **Investigator app** (a Google Maps/Earth-style map with an Ask panel) on live data:

```bash
uv pip install -e ".[serve]"
ollama pull qwen2.5:7b  # optional: lets it understand free-form questions (free, local)
geoask serve            # → http://127.0.0.1:8787/app/
```

Ask in your own words, about **any place on Earth** or an area you **draw on the map**, e.g. *"What is being built here?"*, *"Has the forest near Tengah shrunk over
the last few years?"*, *"Did they build anything new at Changi Airport since 2018?"*

- **Qwen 2.5 7B (via Ollama)** reads the question and chooses a tool with simple arguments (topic,
  place, years). Python checks them and turns them into date windows. Years count only if you gave
  them; open questions always use the Clay "any change" tool.
- **Numbers can't be invented:** the model writes the answer from a list of measured facts, and
  every number in its text is checked against those facts. If any number isn't found, a fixed-wording
  answer is shown instead, and the app says so.
- Without Ollama, a rule-based planner takes over automatically.

**Clay foundation model** (optional, about 0.6 GB on disk): ask open questions like *"What changed in
Tengah since 2019?"* and Clay v1.5 looks for change of any kind, patch by patch:

```bash
uv pip install -e ".[ml,serve]"
python scripts/fetch_clay.py      # downloads 5.2 GB once, keeps the 0.6 GB fp16 encoder, deletes the rest
```

| Check (Tengah, 2019-01-01 → 2026-03-25) | Result |
|---|---|
| Clay patch distance vs independent NDVI change, ROC-AUC over 2,254 patches (80 m) | **0.926** |
| Changed area: Clay (any kind) / NDVI (vegetation loss + gain) | 437 ha / 264 ha |
| Clay v1.5 on an M3 (MPS, fp32): load / four 256 px chips | 3.7 s / ~1.5 s |

Clay finds more than NDVI because it also sees bare-earth-to-building change, which a vegetation
index can't. Reproduce with `python scripts/eval_clay_vs_ndvi.py tengah 2019-01-01/2019-12-31 2026-01-01/2026-11-20`.

Outputs (PNG quicklooks, a GeoTIFF change layer and `result.json`) go to `out/`. A read cache in
`~/.cache/geoask` is capped at 500 MB (`GEOASK_CACHE_MB`). Raw scenes are never stored.

## Design

| | |
|---|---|
| **Works with any sensor** | Instrument profiles (`profiles/*.yaml`, or generated from STAC metadata) describe the bands by wavelength. |
| **No keys** | Public STAC catalogues plus COGs on AWS open data and Planetary Computer (anonymous token). |
| **Trustworthy numbers** | The language model plans; deterministic tools compute; answers cite their scenes and the clear-pixel percentage. |
| **Foundation models, any of them** | One `GeoEncoder` interface and registry (`geoask.models`). **Clay v1.5 runs today** (a ported encoder, so no Lightning/timm dependencies). Adapters are declared for Prithvi-EO-2.0, DOFA, TerraMind, Galileo and Copernicus-FM, and a weight-free spectral baseline runs too. Fixed-band models get bands matched by wavelength; embeddings are tagged by model so they never mix. Third-party models plug in through the `geoask.models` entry point. |
| **Cloud and haze checks** | The sensor's own mask, plus an independent spectral haze test (Fmask HOT and whiteness) that re-ranks dates. Vendor masks miss haze over the strait. |
| **Super-resolution** *(planned)* | 2.5 m view with a consistency-checked confidence map. Display only; never used for measurements. |
| **Platforms** | `geoask-py` on Linux and macOS; a native iPhone and Mac app optimised for Apple silicon (Core ML, Foundation Models). |

## Data and attribution

Contains modified Copernicus Sentinel data, processed by GeoAsk. Sentinel-2 L2A via Element84 Earth
Search (AWS Open Data); Sentinel-1 RTC via Microsoft Planetary Computer. Place boundaries are
currently approximate bounding boxes.

## License

MIT
