# Meshtastic Site Planner -- Known Issues & Improvements

This document catalogs all identified issues and improvement opportunities, organized by priority.

---

## P0 -- Critical (Security)

### 1A: No rate limiting on `/predict`

**File:** `app/main.py`

The `/predict` endpoint accepts requests without any rate limiting. Each request spawns a SPLAT! subprocess (CPU-intensive, runs 30-60 seconds). An attacker or misbehaving client can trivially exhaust server resources by spamming this endpoint.

**Recommendation:** Add per-IP rate limiting using `slowapi` or a Redis-based counter. Suggested limit: 5 requests per minute per IP.

---

### 1B: `task_id` accepts arbitrary strings in path parameters

**File:** `app/main.py`

The `/status/{task_id}` and `/result/{task_id}` endpoints accept any string as `task_id`, which is passed directly into Redis key lookups. While Redis key injection is low-risk here, accepting arbitrary strings violates the principle of least privilege and could be used for enumeration or abuse.

**Recommendation:** Validate `task_id` as a UUID using Python's `uuid.UUID` type in the FastAPI path parameter.

---

### 1C: Docker container runs as root

**File:** `Dockerfile`

The container runs all processes as `root`. If an attacker exploits a vulnerability in the application, they gain root access inside the container, increasing the blast radius.

**Recommendation:** Create a non-root user (`appuser`) and switch to it before the `CMD`/entrypoint.

---

### 1D: Redis has no authentication and is exposed on port 6379

**File:** `docker-compose.yml`

Redis is started with no password and its port is published to the host (`6379:6379`). Any process on the host (or network, depending on firewall) can read/write/flush the Redis instance.

**Recommendation:** Remove the `ports` mapping for Redis (it only needs to be reachable within the Docker network). Add `requirepass` via Redis config or command args.

---

### 1E: CORS has invalid wildcard and uses HTTP for production origin

**File:** `app/main.py`

The CORS `allow_origins` list contains `"http://localhost:*/"` which is not a valid origin (wildcards are not supported in origin strings by the CORS spec or Starlette). The production origin `"http://site.meshtastic.org"` uses HTTP instead of HTTPS.

**Recommendation:** Replace with explicit origins (`"http://localhost:5173"`, `"https://site.meshtastic.org"`) and drive the list from an `ALLOWED_ORIGINS` environment variable.

---

## P1 -- High Priority (Architecture & UX)

### 2A: `store.ts` is a monolith

**File:** `src/store.ts` (403 lines)

The Pinia store handles map initialization, tile layers, simulation API calls, PDF export with multi-tile stitching, GeoRaster rendering, and marker management -- all in one file. This makes the code hard to test, reason about, and maintain.

**Recommendation:** Decompose into focused modules:
- `stores/map.ts` -- map init, tile layers, base layer tracking
- `stores/simulation.ts` -- API calls, polling, state
- `stores/sites.ts` -- local sites, raster layers
- `composables/useExport.ts` -- PDF export logic

---

### 2B: Map initialization happens inside `Transmitter.vue`

**File:** `src/components/Transmitter.vue`

The map is initialized from a child component rather than the layout root. This couples the map lifecycle to a specific form component and creates fragile ordering dependencies.

**Recommendation:** Move map initialization to `App.vue` or a dedicated `MapContainer.vue` component that owns the map element's lifecycle.

---

### 2C: Pervasive `any` types

**Files:** `src/store.ts`, `src/types.ts`

The `raster` and `rasterLayer` fields use `any` throughout. GeoRaster properties are accessed with `as any` casts. This eliminates TypeScript's ability to catch bugs at compile time.

**Recommendation:** Define proper interfaces for `GeoRaster` and `GeoRasterLayer` based on their actual shape. Add a `src/types/georaster.d.ts` declaration file.

---

### 2D: `JSON.parse(JSON.stringify())` used for deep cloning

**File:** `src/utils.ts`

The `cloneObject()` function uses `JSON.parse(JSON.stringify(item))` which silently drops `undefined`, `Date`, `RegExp`, `Map`, `Set`, functions, and circular references. Modern runtimes support `structuredClone()` which handles these correctly.

**Recommendation:** Replace with `structuredClone(item)`.

---

### 3A: Users must manually enter all device specifications

**Files:** `src/store.ts`, `src/components/Transmitter.vue`

Users must know and manually enter TX power, frequency, antenna gain, and receiver sensitivity. Meshtastic has a finite set of well-known device and channel configurations that could be offered as presets.

**Recommendation:** Add a device/channel preset selector that auto-fills parameters (e.g., Heltec V3 on LongFast, RAK WisBlock on MediumSlow).

---

### 5B: Form validation is not wired up

**Files:** `src/components/Transmitter.vue`, `src/components/Simulation.vue`

Forms use `novalidate` attribute alongside `required` fields, but no JavaScript validation logic is implemented. Users can submit empty or invalid values.

**Recommendation:** Either remove `novalidate` to enable native HTML validation, or implement proper JavaScript validation with user-facing error messages.

---

### 6A: No linting or formatting configuration

**Files:** `package.json`, project root

There is no ESLint, Prettier, or any other linting/formatting tool configured. Code style is inconsistent (mixed semicolons, inconsistent brace placement, inconsistent quoting).

**Recommendation:** Add ESLint with `@vue/eslint-config-typescript` and Prettier. Add lint scripts to `package.json` and a pre-commit hook.

---

## P2 -- Medium Priority (Features & Quality)

### 3B: No save/load functionality

All simulation work is lost when the browser tab is closed. There is no mechanism to save site configurations or results to local storage, a file, or a server.

**Recommendation:** Implement save/load using `localStorage` (already partially commented out in `store.ts` via `useLocalStorage`) or file export/import (JSON).

---

### 3C: No coverage statistics after simulation

After a simulation completes, the user sees only the visual overlay. There are no summary statistics such as total area covered, percentage at various signal levels, or min/max/mean signal strength.

**Recommendation:** After GeoRaster parsing, compute and display coverage statistics (area by signal level, histogram, percentage above threshold).

---

### 5A: Color scale legend only visible in side panel

The color scale that maps colors to dBm values is only shown in the side panel form, not on the map itself. When the panel is collapsed or the user is focused on the map, the legend is not visible.

**Recommendation:** Add a Leaflet map control that displays the color scale legend directly on the map.

---

### 5D: "Set with Map" provides no visual feedback

When the user clicks "Set with Map" to place the transmitter, there is no crosshair cursor, instruction text, or other indication that the map is now in placement mode.

**Recommendation:** Show a crosshair cursor, a floating instruction ("Click on the map to set transmitter location"), and revert after placement.

---

### 5C: Only a spinner during long simulations

Simulations take 30-60 seconds. The only feedback is a spinner with no progress indication. Users have no way to know if the simulation is 10% or 90% done.

**Recommendation:** Add progress reporting from the backend (write progress percentage to Redis, read it in the polling response) or at minimum show elapsed time.

---

### 6B: Zero backend tests

**File:** `app/`

There are no tests for the backend. The SPLAT! service orchestration, GeoTIFF generation, and API endpoints are untested.

**Recommendation:** Add pytest tests for the API endpoints (mock SPLAT! subprocess) and unit tests for the service layer.

---

### 6C: No frontend tests

**File:** `src/`

There are no frontend tests of any kind -- no unit tests, no component tests, no E2E tests.

**Recommendation:** Add Vitest for unit/component tests. Add Playwright or Cypress for E2E tests.

---

### 6D: No CI pipeline

There is no GitHub Actions, GitLab CI, or any other CI configuration. Builds, tests, and linting are not automated.

**Recommendation:** Add a GitHub Actions workflow that runs lint, type-check, unit tests, and builds the frontend on every PR.

---

## P3 -- Performance

### 4A: Heavy libraries loaded eagerly

**File:** `src/store.ts`

`html2canvas`, `georaster`, and `georaster-layer-for-leaflet` are imported at the top of `store.ts` and included in the initial bundle. `jsPDF` is already lazy-loaded via dynamic `import()` inside `exportMap()`, but the others are not.

**Recommendation:** Use dynamic `import()` for `html2canvas`, `georaster`, and `georaster-layer-for-leaflet` at their point of use.

---

### 4B: Polling `/status/` every 1 second

**File:** `src/store.ts`

The frontend polls `/status/{task_id}` every 1 second using `setTimeout`. This creates unnecessary network traffic and server load, especially with multiple concurrent users.

**Recommendation:** Replace polling with Server-Sent Events (SSE) from the backend, or at minimum use exponential backoff.

---

### 4C: GeoTIFF parsing blocks the main thread

**File:** `src/store.ts`

`parseGeoraster(arrayBuffer)` runs on the main thread and can block the UI for large rasters.

**Recommendation:** Move GeoTIFF parsing to a Web Worker to keep the UI responsive.

---

### 4D: BackgroundTasks is single-threaded

**File:** `app/main.py`

FastAPI's `BackgroundTasks` runs tasks in the same event loop thread (or a single thread pool). With multiple concurrent prediction requests, tasks queue up sequentially. The project already has Celery dependencies installed (`celery`, `kombu`, `amqp`, `billiard` in `requirements.txt`).

**Recommendation:** Migrate `run_splat` to a Celery task using the already-installed dependencies. Use Redis as the Celery broker.

---

## P4 -- DevOps

### 7A: No `.dockerignore` file

**File:** (missing)

The Dockerfile uses `COPY . .` which copies everything including `node_modules/`, `.git/`, IDE config, and other unnecessary files into the image. This bloats the image and can leak sensitive data.

**Recommendation:** Create a `.dockerignore` with: `node_modules`, `.git`, `*.md`, `.vscode`, `.claude`, `.playwright-mcp`, `__pycache__`, `*.pyc`, `.env`.

---

### 7B: Multiple `RUN chmod` commands create unnecessary layers

**File:** `Dockerfile`

Six separate `RUN chmod +x` commands each create a new image layer, increasing image size and build time.

**Recommendation:** Consolidate into a single `RUN` command.

---

### 7C: No Docker health check

**File:** `Dockerfile`

There is no `HEALTHCHECK` instruction. Docker and orchestrators cannot automatically detect if the application is unresponsive.

**Recommendation:** Add `HEALTHCHECK CMD curl --fail http://localhost:8080/ || exit 1` or use a dedicated `/health` endpoint.

---

### 7D: No dev/prod Docker Compose split

**File:** `docker-compose.yml`

A single `docker-compose.yml` is used for both development and production. Development concerns (volume mounts, port exposure, debug settings) are mixed with production concerns (SSL, nginx proxy).

**Recommendation:** Split into `docker-compose.yml` (base), `docker-compose.dev.yml` (overrides for dev), and `docker-compose.prod.yml` (overrides for prod).
