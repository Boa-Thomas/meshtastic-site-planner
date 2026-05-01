# Meshtastic Site Planner

[![CLA assistant](https://cla-assistant.io/readme/badge/meshtastic/meshtastic-site-planner)](https://cla-assistant.io/meshtastic/meshtastic-site-planner)

**Live:** https://site.meshtastic.org

Plan and simulate Meshtastic mesh networks using real terrain data. Combines physics-based RF propagation (ITM/Longley-Rice via SPLAT!) with a discrete-event simulation (DES) engine that models the Meshtastic protocol — managed flood routing, LoRa airtime, contention windows, and multi-hop delivery — to predict both coverage area and network behavior.

## What It Does

1. **RF Coverage Prediction** — Place transmitter sites on a map, configure device and antenna parameters, and run SPLAT! simulations against NASA SRTM terrain elevation data. The result is a GeoTIFF overlay showing received signal strength (dBm) across the coverage area.

2. **Mesh Network Simulation (DES)** — Define mesh nodes with real device presets (Heltec V3, RAK WisBlock, T-Beam, Station G2, etc.), choose a LoRa channel preset (SHORT_TURBO through VERY_LONG_SLOW), and simulate how packets propagate through the network. The DES engine calculates link budgets, models collisions and contention, and tracks delivery rates, hop counts, and latency across the mesh.

3. **Hybrid Analysis** — SPLAT! raster data can feed into the DES engine as RSSI overrides, replacing free-space path loss estimates with terrain-aware signal strength. This produces simulations calibrated against real propagation conditions.

### Calibration Results

The simulation has been validated against real-world field data from a mesh network in the Serra Catarinense / Grande Florianopolis region (Brazil), using 8 nodes across distances of 2–50 km with elevation differences up to 1200 m:

| Node | Elevation | AGL | Simulated Coverage | Notes |
|------|-----------|-----|--------------------|-------|
| Cambirela | 1280 m | 2 m | 9.06% | Summit site — covers coastal strip east with clear LOS; blocked westward by Serra |
| Pedra Branca | 450 m | 10 m | 4.12% | Hilltop in Grande Floripa — local links validated (Muller, Rancho SV) |
| Morro Azul | 1050 m | 8 m | 0.98% | Mountain site — eliminated phantom coverage in distant valleys |
| Drone relay | 120 m AGL | — | 0.57% | Height advantage: ~5x coverage vs ground nodes at 18 m |
| Sao Bernardo | 850 m | 5 m | 0.14% | Deep valley — correctly shows marginal coverage |
| a65c | est. | est. | 0.03% | Multi-hop node — real SNR +6.2 dB via 3 hops |
| a8cc | est. | est. | 0.01% | Marginal signal — real reception only via 2+ hops |

Key calibration corrections included dual-slope path loss (steeper attenuation beyond a breakpoint distance), directional cosine-squared antenna modeling for window installations, and per-channel receiver sensitivity aligned with LoRa theoretical values.

## Features

- **Interactive map** — Leaflet-based with click-to-place nodes and sites
- **11 device presets** — Heltec V3/V4, RAK WisBlock 4631/11310, T-Beam v1.2/Supreme, T-Echo, T-Deck, Station G2, Wireless Paper, TLORA T3 S3
- **9 channel presets** — SHORT_TURBO (-108 dBm) through VERY_LONG_SLOW (-132 dBm) with accurate SF/BW/CR parameters
- **6 antenna presets** — Stock stubby, quarter-wave whip, 5/6 dBi omni, 9/12 dBi Yagi with beamwidth modeling
- **Installation types** — Rooftop, mast, window (with azimuth cone), portable
- **Pluggable terrain pipeline** — Switch between SRTM (default), Copernicus GLO-30 DSM, and FABDEM (DTM, no canopy/buildings) via env or per request
- **Spatial clutter** — Per-pixel canopy height (Lang 2023, MapBiomas) folded into a synthetic DSM, plus a calibration pipeline to fit the penetration factor against real RSSI
- **DES visualization** — Real-time event log, link overlay on map, per-node metrics, traceroute view
- **Project save/load** — Export full project state (nodes, sites, raster overlays, DES config) as compressed `.json.gz`
- **PDF export** — Generate coverage map reports with html2canvas + jsPDF
- **SPLAT! raster persistence** — IndexedDB caching of coverage overlays across sessions

## Quick Start

### Production

Go to https://site.meshtastic.org — no installation required.

### Development

Requirements: Node.js 18+, pnpm, Docker, Docker Compose, Git.

```bash
git clone --recurse-submodules https://github.com/meshtastic/meshtastic-site-planner
cd meshtastic-site-planner
pnpm i
pnpm run dev        # Frontend dev server with hot reload (proxies API to :8080)
```

### Full Stack (with SPLAT! backend)

```bash
# Linux/Mac
./setup.sh

# Windows
setup.bat
```

Or manually:

```bash
cp .env.example .env        # Review and adjust settings
docker compose up --build   # Build SPLAT! + start all services
```

This compiles the SPLAT! C++ binary (with MAXPAGES=225 for up to 600 km radius), starts FastAPI, Redis, Celery workers, autoscaler, Nginx, and Let's Encrypt.

### Tests

```bash
pnpm test           # Vitest in watch mode (243 tests)
pnpm test:e2e       # Playwright E2E tests
```

## Architecture

```
Frontend (Vue 3 + TypeScript + Pinia)
├── Map layer         Leaflet + GeoRaster overlays + custom markers
├── Stores            mapStore, sitesStore, nodesStore, desStore
├── DES Engine        Pure TypeScript discrete-event simulation
│   ├── SimulationEngine    Event loop with priority queue
│   ├── LinkBudget          FSPL + dual-slope + directional model
│   ├── AirtimeCalculator   LoRa Semtech airtime formula
│   ├── ContentionWindow    SNR-based delay (Meshtastic protocol)
│   ├── ChannelModel        Collision detection
│   └── MeshtasticProtocol  Managed flood routing, dedup, ACK
└── Components        NodeEditor, NodeList, InstallationConfig,
                      DesControls, DesMetrics, DesEventLog, DesLinkOverlay

Backend (FastAPI + Python)
├── POST /predict             Submit coverage prediction request
├── GET  /status/{id}         Poll task status
├── GET  /events/{id}         SSE stream for real-time task updates
├── GET  /result/{id}         Download GeoTIFF result
├── GET  /api/settings/terrain         Active DEM/clutter config visible to UI
├── POST /api/calibration/measurements Submit ground-truth RSSI
├── GET  /api/calibration/summary      Aggregate by DEM/clutter
└── SPLAT! pipeline   DEM download → optional clutter overlay →
                      HGT→SDF → SPLAT! → PPM+KML → GeoTIFF

Infrastructure
├── Docker Compose    app + redis + nginx-proxy + acme-companion
│                     + worker (light) + worker-heavy + autoscaler + flower
├── AWS S3            SRTM terrain tile streaming
└── Redis             Task queue, result cache, Celery broker
```

### Worker Architecture

Simulations are processed by Celery workers split into two queue types:

| Service | Queue | Memory | Default Replicas | Purpose |
|---------|-------|--------|-----------------|---------|
| `worker` | `default` | 4 GB | 2 | Simulations up to 200 km |
| `worker-heavy` | `heavy,default` | 8 GB | 1 | Simulations over 200 km (also helps with default queue) |

An **autoscaler** service monitors Redis queue depth and dynamically scales workers via the Docker API:

- **Idle:** 1 light + 1 heavy workers (minimum baseline)
- **Under load:** Up to 4 light + 3 heavy = 7 parallel workers
- **Cooldown:** Scales down to baseline after 120s of empty queues

### Terrain Pipeline

The DEM source and the optional spatial-clutter layer are pluggable. By
default `DEM_SOURCE=srtm` keeps the historical behaviour; switch to
`copernicus` (public AWS Open Data) or `fabdem` (operator-hosted DTM
mirror) without code changes. When clutter is enabled, canopy heights are
folded into a synthetic DSM before SPLAT! runs, so vegetation is treated
as terrain instead of via the uniform `-gc` knob.

| Source | Type | Where it comes from |
|--------|------|---------------------|
| `srtm` | DSM, 30 m | Public AWS bucket `elevation-tiles-prod` (default) |
| `copernicus` | DSM, 30 m | Public AWS bucket `copernicus-dem-30m` |
| `fabdem` | DTM, 30 m | Your S3 mirror (CC BY-NC-SA — not redistributable) |
| `lang2023` (clutter) | Canopy, 10 m | Your S3 mirror (Lang et al. 2023) |
| `mapbiomas` (clutter) | Canopy, 30 m | Your S3 mirror (MapBiomas, BR-only) |

Operator workflow:

1. **Mirror tiles** with the bundled CLI (no app deps required):
   ```bash
   python utils/mirror_terrain.py ingest \
       --dataset fabdem --bbox=-25,-49,-23,-46 \
       --source-url "https://example.org/{tile}_FABDEM_V1-2.tif" \
       --dest-bucket my-mirror --dest-prefix fabdem-v1-2
   ```
   `list` enumerates required tiles, `verify` audits a populated bucket.

2. **Configure** by setting `DEM_SOURCE`, `FABDEM_BUCKET`, `CLUTTER_SOURCE`,
   `CLUTTER_BUCKET`, etc. in `.env`. Workers and the API container read the
   same vars (see `docker-compose.yml`). Per-request override is also
   supported — `POST /predict` accepts optional `dem_source`,
   `clutter_source` and `clutter_penetration_factor` fields, surfaced in
   the UI under "Terrain & Clutter".

3. **Calibrate** the penetration factor. The default of `0.6` is a
   placeholder. Once you have ≥ 30 ground-truth RSSI points (submit them
   via `POST /api/calibration/measurements`), run:
   ```bash
   python utils/calibrate_clutter.py \
       --api-base http://localhost:8080 \
       --dem-source fabdem --clutter-source lang2023 \
       --factors 0.3,0.4,0.5,0.6,0.7,0.8
   ```
   The script picks the factor with lowest MAE and writes a JSON report.
   After updating `CLUTTER_PENETRATION_FACTOR` in `.env`, set
   `CLUTTER_FACTOR_CALIBRATED=true` to remove the "uncalibrated" UI
   warning.

The result cache is namespaced by `(dem_source, clutter_source, factor)`
quantized to 0.01, so different combinations never share tiles. You can
A/B test sources without invalidating each other.

See [docs/dem-roadmap.md](docs/dem-roadmap.md) for design notes.

### Environment Variables

Copy `.env.example` to `.env` and adjust as needed. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CELERY_LIGHT_WORKERS` | `2` | Initial light worker replicas |
| `CELERY_HEAVY_WORKERS` | `1` | Initial heavy worker replicas |
| `WORKER_LIGHT_MEM` | `4G` | Memory limit per light worker |
| `WORKER_HEAVY_MEM` | `8G` | Memory limit per heavy worker |
| `MAX_LIGHT_WORKERS` | `4` | Maximum light workers (autoscaler) |
| `MAX_HEAVY_WORKERS` | `3` | Maximum heavy workers (autoscaler) |
| `HEAVY_RADIUS_THRESHOLD_KM` | `200` | Radius threshold for heavy queue routing |
| `MAX_SIMULATION_RADIUS_KM` | `600` | Maximum simulation radius |
| `SCALE_DOWN_DELAY` | `120` | Seconds before autoscaler reduces workers |
| `DEM_SOURCE` | `srtm` | Elevation source: `srtm`, `copernicus`, or `fabdem` |
| `FABDEM_BUCKET` | _(empty)_ | S3 bucket holding your FABDEM mirror |
| `FABDEM_FALLBACK_SOURCE` | `copernicus` | DEM used when a FABDEM tile is missing |
| `CLUTTER_SOURCE` | `none` | `none`, `lang2023`, `mapbiomas`, or `custom` |
| `CLUTTER_BUCKET` | _(empty)_ | S3 bucket holding your canopy-height tiles |
| `CLUTTER_PENETRATION_FACTOR` | `0.6` | Canopy height multiplier (placeholder until calibrated) |
| `CLUTTER_FACTOR_CALIBRATED` | `false` | Set `true` once factor is fitted to field data |

See `.env.example` for the full list.

## Usage

### Coverage Prediction (SPLAT!)

1. Click on the map or enter coordinates to place a transmitter site
2. Configure TX parameters: device preset, antenna height (AGL), transmit power, frequency
3. Configure RX parameters: sensitivity (based on channel preset), receiver height, antenna gain
4. Set simulation range (km) and resolution
5. Press **Run Simulation** — the coverage heatmap renders when computation completes
6. Add multiple sites to visualize combined network coverage

### Mesh Simulation (DES)

1. Click on the map to place mesh nodes, or import a project file
2. Select device preset, channel preset, and antenna for each node
3. Configure installation type (rooftop, mast, window with azimuth, portable)
4. Open the DES panel to configure simulation parameters
5. Run the simulation to see packet delivery metrics, link quality, hop counts, and event timeline
6. Use the link overlay to visualize active connections on the map

### Hybrid Workflow

1. Run SPLAT! coverage for key sites first
2. Place mesh nodes in covered areas
3. The DES engine automatically uses SPLAT! RSSI data (when available) instead of FSPL estimates
4. Compare simulated metrics against real-world field measurements

## Model and Assumptions

This tool runs physics-based RF simulations with the following assumptions:

1. **Terrain model** — NASA SRTM data at 90 m resolution. Does not account for buildings, vegetation, or other above-ground obstructions.
2. **Propagation model** — ITM/Longley-Rice (SPLAT!) for coverage prediction; Free Space Path Loss with optional dual-slope extension for DES link budgets.
3. **Antenna model** — Omnidirectional in horizontal plane by default. Directional antennas use cosine-squared gain pattern. Window installations support azimuth cone restriction.
4. **Protocol model** — DES implements Meshtastic managed flood routing with realistic airtime, contention windows, and hop limits.
5. **Atmospheric effects** — No skywave propagation (valid above ~50 MHz). No precipitation or atmospheric ducting modeling.

For detailed parameter documentation, see [parameters.md](parameters.md).

## Contributing

Contributions welcome. Please sign the CLA via the CLA assistant when opening your first PR.

## License

See [LICENSE](LICENSE) for details.
