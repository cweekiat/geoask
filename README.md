# GeoAsk

**A sensor-agnostic platform for geospatial foundation models: satellite imagery analysis,
change detection and pattern-of-life detection, asked in plain language.**

GeoAsk turns a question such as *"What has changed at the Tesla Gigafactory Berlin since 2019?"*,
*"How busy is this anchorage, pass by pass?"* or *"What can a 10 m mast at 48N UG 6387 4975 see?"*
into a plan, runs measured tools on open satellite data, and answers with numbers, maps and the
exact scenes used. It works **anywhere on Earth**, with **any sensor** whose bands are described by
wavelength, and with **any geospatial foundation model** (GFM) that implements one small interface.
It runs on a laptop with no API keys.

**[Try the Investigator demo →](https://cweekiat.github.io/geoask/app/)** Demo mode on GitHub Pages
replays a recorded live run for every tool (built with `scripts/build_gallery.py`); run
`geoask serve` for live analysis.

In the app: a **tool gallery** with one example per tool; **quick actions** (any change,
vegetation, vessels, terrain, sharpen) when you draw an area; a **point card** on right-click
(all coordinate formats, elevation, *Viewshed From Here*, *Measure From Here*); and **line of
sight** with an elevation profile from the measure tool.

> **The rule:** a language model chooses which tools to run; deterministic code computes every
> number from native-resolution pixels. Every number in the written answer is checked against the
> measurements before it's shown.

## What it does

| Capability | How | Data |
|---|---|---|
| **Change of any kind** | Foundation-model embeddings compared patch by patch (Clay v1.5 today), Otsu threshold | Sentinel-2 L2A, 10 m |
| **Targeted change** | Spectral indices: vegetation, water and coastline, built-up land | Sentinel-2 (or any sensor with the bands) |
| **Pattern of life at sea** | Vessels on every radar pass (CFAR detector with SAHI-style slicing), each pass judged against its own orbit, robust anomaly flags, density map, persistent targets set aside | Sentinel-1 RTC, 10 m, day/night, through cloud |
| **Terrain** | Elevation, slope, relief; viewshed with Earth curvature and refraction; line of sight | Copernicus GLO-30 DEM |
| **Super-resolution (display only)** | SEN2SR-Lite 10 m → 2.5 m, physically constrained, with a consistency map | Sentinel-2 RGB + NIR |
| **Mapping** | MGRS grid (zones, 100 km, 10 km, 1 km), coordinates in decimal / DMS / MGRS / UTM, distance and bearing (true and mils), point cards with elevation, coordinate search, hillshade, 3D terrain and buildings | OpenStreetMap, AWS Terrain Tiles |
| **Any place** | Curated areas → bundled offline gazetteers → OpenStreetMap Nominatim (keyless, cached), or draw a box | Global |

## Architecture

```
question ─▶ planner (Qwen 2.5 7B via Ollama, or rule-based) ─▶ tool call (validated in Python)
                                                                   │
  ┌────────────────────────────── tools ───────────────────────────┴──────────────────────┐
  │ index_change · embedding_change · activity · terrain · viewshed · super_resolve        │
  └──────┬──────────────────────┬─────────────────────────┬───────────────────────────────┘
         │                      │                         │
  GFM registry            detector interface        super-resolution interface
  (geoask.models)         + SAHI-style slicing      (geoask.models.superres)
  Clay v1.5 ✓, Prithvi,   CFAR vessels ✓,           SEN2SR-Lite ✓
  DOFA, TerraMind,        any SAHI model
  Galileo, Copernicus-FM  (YOLO, torchvision, HF)
         │                      │                         │
  ┌──────┴──────────────────────┴─────────────────────────┴───────────────────────────────┐
  │ data layer: STAC search → COG window reads → one UTM grid per area → cloud/haze masks │
  │ instrument profiles (profiles/*.yaml): bands by wavelength, not by name               │
  └────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Sensor-agnostic.** Tools ask for `red`, `nir`, `swir1` or `vv`; the instrument profile finds the
  nearest band by wavelength and refuses rather than guesses. Profiles can be generated from STAC
  metadata, so a new sensor is a YAML file, not code.
- **Model-agnostic.** A `GeoEncoder` declares the bands it needs (or `bands="any"` for
  wavelength-aware models such as DOFA), and GeoAsk feeds it. Embeddings are tagged with
  model@version and never mixed. Third-party models register through the `geoask.models` entry
  point. Detectors and super-resolution models plug in the same way.
- **Anywhere on Earth.** Each area is analysed on the WGS84/UTM grid of its own zone, so a 10 m
  pixel is 10 m everywhere. No national datasets are used.
- **Low data footprint.** Only the pixels for the area are streamed (HTTP range reads); raw scenes
  are never stored; the read cache is capped at 500 MB.

## Quick start (Linux or macOS)

```bash
git clone https://github.com/cweekiat/geoask && cd geoask
uv venv && uv pip install -e ".[serve]"
ollama pull qwen2.5:7b        # optional: free-form questions, runs locally
geoask serve                  # → http://127.0.0.1:8787/app/
```

Optional models:

```bash
uv pip install -e ".[ml]"
geoask fetch sen2sr           # super-resolution weights, 3.4 MB, CC0
python scripts/fetch_clay.py  # Clay v1.5: downloads 5.2 GB once, keeps the 0.6 GB fp16 encoder
```

From the command line (places are any name on Earth, or `--bbox W S E N`):

```bash
geoask change   --place tengah --index ndvi --t0 2019-01-01/2019-12-31 --t1 2025-01-01/2025-11-30
geoask activity --bbox 103.74 1.20 103.86 1.26 --window 2026-08-01/2026-11-20
geoask viewshed --at "48N UG 6387 4975" --radius 3000 --height 10
geoask terrain  --place "Mount Faber"
geoask sharpen  --place "marina bay" --window 2026-01-01/2026-11-20
geoask mgrs 1.3521 103.8198
```

## Results so far

| Check | Result |
|---|---|
| Clay patch distance vs independent NDVI change, Tengah 2019 → 2026, ROC-AUC over 2,254 patches (80 m) | **0.926** |
| Tesla Gigafactory Berlin (UTM 33N), Clay, 2019-04-02 → 2025-11-21 | 117 ha of a 349 ha box changed |
| Vessels per Sentinel-1 pass, western anchorages off Singapore, Aug–Nov 2026 (6 passes) | 18–76 per pass; 2026-10-10 flagged busier |
| Viewshed, 10 m mast on Bukit Timah, 3 km radius | 1,589 ha (56%) visible |
| SEN2SR-Lite, Marina Bay: 2.5 m output averaged back to 10 m vs the real pixels | mean difference 0.002 reflectance |
| UTM and MGRS (Python and the web app's JavaScript) vs PROJ | < 1 mm; MGRS identical on 505 test points, including the Norway/Svalbard zones |

## Honest limits

- 10 m pixels: objects under about 20–30 m (small boats, single houses) are often missed.
- Radar detections are **bright targets on water**, not identities. There's no AIS or ADS-B.
- GLO-30 is a *surface* model: heights include buildings and tree canopy, and the viewshed treats
  them as solid.
- Super-resolved images are for viewing; GeoAsk never measures from them.
- Cloud masks miss some haze; dates are re-ranked with an independent spectral haze test.

## Data and attribution

Contains modified Copernicus Sentinel data, processed by GeoAsk (Sentinel-2 L2A via Element84 Earth
Search on AWS Open Data; Sentinel-1 RTC via Microsoft Planetary Computer). Copernicus GLO-30 DEM:
© DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under COPERNICUS by
the European Union and ESA. Place names and map data © OpenStreetMap contributors (ODbL). SEN2SR
(ESA OpenSR / TACO foundation), CC0-1.0. Yearly mosaics: Sentinel-2 cloudless by EOX. High-resolution
basemap © Esri, Maxar (display only). Terrain tiles: Mapzen / AWS. Clay v1.5 (Apache-2.0).

Design notes: [docs/PLAN.md](docs/PLAN.md) (scope and decisions) and [docs/DESIGN.md](docs/DESIGN.md)
(interface and Human Interface Guidelines review).

## License

MIT
