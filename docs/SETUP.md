# Setup Guide

End-to-end walkthrough: clone → run → optional terrain pipeline → calibration.

If you only need the live app, go to https://site.meshtastic.org. This guide
is for operators self-hosting the backend.

## 1. Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Git | any | Clone + submodule (SPLAT! source) |
| Docker | 24+ | Builds the SPLAT! C++ binary and runs the stack |
| Docker Compose | v2 plugin or standalone | Multi-service orchestration |
| Node.js | 18+ | Frontend dev server (only if you'll touch the UI) |
| pnpm | 8+ | Same — frontend package manager |
| Python | 3.10+ | Running the operator CLIs (`utils/*.py`) outside Docker |

The Python utilities (mirror ingestion, calibration solver) need:

```bash
pip install boto3 requests rasterio numpy
```

`rasterio` is optional but recommended — without it, mirror validation falls
back to a TIFF-magic check only.

## 2. Clone

The SPLAT! C++ source lives in a submodule. Use `--recurse-submodules`:

```bash
git clone --recurse-submodules https://github.com/meshtastic/meshtastic-site-planner
cd meshtastic-site-planner
```

If you forgot `--recurse-submodules`, fix it after the fact:

```bash
git submodule update --init --recursive
```

## 3. Start the stack

### 3a. Frontend-only (proxies API to a local backend)

```bash
pnpm install
pnpm run dev
```

Vite serves on `http://localhost:5173` and proxies `/predict`, `/api/*`, etc.
to `http://localhost:8080` — start the backend separately.

### 3b. Full stack (Docker, recommended)

The bundled setup script handles submodules, `.env` creation, and `docker
compose up --build`:

```bash
# Linux / macOS
./setup.sh

# Windows
setup.bat
```

Or manually:

```bash
cp .env.example .env        # Edit if needed (defaults work for SRTM)
docker compose up --build   # First build is ~10–15 min (compiling SPLAT!)
```

When it's up:

- App: http://localhost:8080
- Flower (Celery dashboard): http://localhost:5555

Smoke test:

```bash
curl http://localhost:8080/api/settings/terrain
# {"defaults":{"dem_source":"srtm","clutter_source":"none", ...}, ...}
```

### 3c. Tear down

```bash
docker compose down            # Stop containers, keep volumes
docker compose down -v         # Also drop volumes (cache + planner DB)
```

## 4. Pick a DEM source

Default is `srtm` — works out of the box, no setup needed. Two upgrades are
available:

### 4a. Switch to Copernicus GLO-30 (zero ops cost)

Public AWS Open Data, no mirror to host. Edit `.env`:

```env
DEM_SOURCE=copernicus
```

Restart: `docker compose up -d`. That's it.

### 4b. Switch to FABDEM (DTM, no canopy/buildings)

FABDEM is CC BY-NC-SA. There's no public AWS Open Data mirror — you must host
the tiles yourself.

1. **Create an S3 bucket** (or any S3-compatible store: Cloudflare R2,
   MinIO, etc.). Keep it private; this is your operator infrastructure.

2. **Acquire FABDEM v1.2** from https://data.bris.ac.uk/data/dataset/25wfy0f9ukoge2gs7a5mqpq2j7
   under the CC BY-NC-SA license. Confirm your use is non-commercial.

3. **Mirror the tiles** with the bundled CLI. Bound the area to what you
   actually serve — global FABDEM is ~150 GB; Brazil-only is ~5 GB.

   ```bash
   # Enumerate tiles needed for São Paulo state
   python utils/mirror_terrain.py list --bbox=-25,-53,-19,-44

   # Ingest from a local directory of FABDEM .tif files
   python utils/mirror_terrain.py ingest \
       --dataset fabdem \
       --bbox=-25,-53,-19,-44 \
       --source-dir ./fabdem-downloads \
       --dest-bucket my-mirror \
       --dest-prefix fabdem-v1-2 \
       --upload-manifest

   # Or ingest from an HTTP URL template
   python utils/mirror_terrain.py ingest \
       --dataset fabdem \
       --bbox=-25,-53,-19,-44 \
       --source-url "https://example.org/fabdem/{tile}_FABDEM_V1-2.tif" \
       --dest-bucket my-mirror \
       --dest-prefix fabdem-v1-2

   # Verify what's there
   python utils/mirror_terrain.py verify \
       --dataset fabdem --bbox=-25,-53,-19,-44 \
       --dest-bucket my-mirror --dest-prefix fabdem-v1-2 --deep
   ```

4. **Configure** `.env`:

   ```env
   DEM_SOURCE=fabdem
   FABDEM_BUCKET=my-mirror
   FABDEM_PREFIX=fabdem-v1-2
   FABDEM_FALLBACK_SOURCE=copernicus     # used per-tile when missing
   ```

5. **Restart** and confirm via the settings endpoint:

   ```bash
   docker compose up -d
   curl http://localhost:8080/api/settings/terrain | jq .dem_sources
   # The "fabdem" entry should have "ready": true
   ```

   The UI ("Terrain & Clutter" panel) will show FABDEM as selectable.

### 4c. (Optional) Add spatial clutter

Same flow, different bucket. Lang 2023 (10 m global canopy heights) is the
recommended default; MapBiomas covers Brazil at 30 m.

```bash
python utils/mirror_terrain.py ingest \
    --dataset lang2023 \
    --bbox=-25,-53,-19,-44 \
    --source-dir ./lang2023-downloads \
    --dest-bucket my-canopy-mirror \
    --dest-prefix lang2023
```

`.env`:

```env
CLUTTER_SOURCE=lang2023
CLUTTER_BUCKET=my-canopy-mirror
CLUTTER_PREFIX=lang2023
CLUTTER_PENETRATION_FACTOR=0.6     # placeholder — calibrate next
```

Restart. The cache namespace now includes the clutter source, so existing
SRTM/Copernicus runs keep their cached tiles.

## 5. Calibrate `CLUTTER_PENETRATION_FACTOR`

The default of `0.6` is a guess. Before trusting clutter-on simulations, fit
the factor against real RSSI from your network.

### 5a. Collect ground-truth measurements

Each measurement is a `(TX → RX, measured RSSI)` tuple plus the RF context.
Submit them to the API:

```bash
curl -X POST http://localhost:8080/api/calibration/measurements \
  -H "Content-Type: application/json" \
  -d '{
    "tx_lat": -23.55, "tx_lon": -46.63,
    "rx_lat": -23.51, "rx_lon": -46.59,
    "rssi_dbm": -98,
    "frequency_mhz": 915,
    "tx_power_dbm": 20, "tx_gain_dbi": 3, "tx_height_m": 6,
    "rx_gain_dbi": 2, "rx_height_m": 1.5,
    "dem_source": "fabdem",
    "clutter_source": "lang2023",
    "clutter_penetration_factor": 0.6,
    "source": "manual",
    "notes": "Cambirela summit → Pedra Branca, clear sky"
  }'
```

Bulk import via shell loop, MQTT bridge, or whatever fits your stack. The API
is permissive — backfill what you have. Aim for **≥ 30 points** before
fitting; below that the result is just noise.

Helpers:

```bash
# List what's stored
curl http://localhost:8080/api/calibration/measurements?limit=100 | jq

# Aggregate by configuration
curl http://localhost:8080/api/calibration/summary | jq
```

### 5b. Run the solver

```bash
python utils/calibrate_clutter.py \
    --api-base http://localhost:8080 \
    --dem-source fabdem \
    --clutter-source lang2023 \
    --factors 0.3,0.4,0.5,0.6,0.7,0.8 \
    --radius-m 15000 \
    --output calibration-result.json
```

The script:

1. Fetches all measurements matching the DEM/clutter filter.
2. For each `(measurement, factor)` combo, submits a `/predict` call,
   downloads the GeoTIFF, samples the predicted RSSI at the RX coordinate.
3. Computes MAE / RMSE / bias per candidate factor.
4. Writes a JSON report and prints the recommended factor.

Cost note: `N measurements × K factors` simulations. Use the local cache
(default `calibration-cache.json`) so re-runs don't repeat work.

Sample output:

```json
{
  "per_factor": [
    { "factor": 0.4, "samples": 32, "mae_db": 12.4, "bias_db": 8.1 },
    { "factor": 0.6, "samples": 32, "mae_db":  6.7, "bias_db": 1.2 },
    { "factor": 0.8, "samples": 32, "mae_db": 10.3, "bias_db": -7.4 }
  ],
  "best": { "factor": 0.6, "mae_db": 6.7 }
}
```

### 5c. Lock it in

Update `.env`:

```env
CLUTTER_PENETRATION_FACTOR=0.6
CLUTTER_FACTOR_CALIBRATED=true
CLUTTER_CALIBRATION_NOTES=Fitted 2026-05-15 from 32 SP/Mata Atlântica points (MAE 6.7 dB)
```

Restart. The "uncalibrated default" warning in the UI disappears.

## 6. Per-request override (optional)

`POST /predict` accepts three optional fields that override the env defaults
for a single request:

```json
{
  "lat": -23.55, "lon": -46.63, ...,
  "dem_source": "fabdem",
  "clutter_source": "lang2023",
  "clutter_penetration_factor": 0.55
}
```

Useful for A/B testing without redeploys. The cache key includes all three so
results don't collide across configurations. The UI exposes these in the
"Terrain & Clutter" panel.

## 7. Verification checklist

After any pipeline change, sanity-check:

```bash
# Settings endpoint reflects your env
curl http://localhost:8080/api/settings/terrain | jq

# A small simulation finishes within ~30 s on a warm cache
curl -X POST http://localhost:8080/predict \
  -H "Content-Type: application/json" \
  -d '{"lat":-23.55,"lon":-46.63,"tx_height":6,"tx_power":20,"frequency_mhz":915,
       "rx_height":1.5,"signal_threshold":-130,"radius":5000,"high_resolution":false}'

# Worker logs show the configured DEM source
docker compose logs --tail=50 worker | grep -i "dem_source"

# Run the full Python test suite
docker compose exec app python -m pytest app/tests/ -q
```

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `FABDEM is selected but FABDEM_BUCKET is not configured` | `DEM_SOURCE=fabdem` without setting the bucket | Set `FABDEM_BUCKET` in `.env`, or revert to `srtm` |
| All FABDEM tiles fall back to Copernicus | Mirror is empty or wrong prefix | Run `mirror_terrain.py verify --deep` |
| Calibration solver returns "no measurements found" | Filters don't match what's in the DB | Drop `--dem-source` / `--clutter-source` to widen the query |
| Workers OOM on large simulations | `WORKER_HEAVY_MEM` too low | Bump to `12G`, scale heavy replicas down to compensate |
| Cache hit rate stays low after switching DEM | Expected — namespaces are isolated by source | Let the cache warm up; it'll hit on subsequent identical requests |

For the design notes behind the pipeline, see
[docs/dem-roadmap.md](dem-roadmap.md).
