# DEM/Clutter Pipeline — 2-Week Follow-up Review (2026-05-15)

Reviewed by: automated review script against commit `724bd5c` (main).

---

## 1. Cache hit metrics — per-source label missing (FIXED in this PR)

**Finding:** `srtm_cache_events_total` (`app/metrics.py:48`) was registered with
`labelnames=("tier", "event")` — no `source` dimension. All three call sites in
`app/services/splat.py` (lines 859, 868, 874) fired without a source label, so
the counter accumulated hits across `srtm`, `copernicus`, and `fabdem` into the
same time series. Queries like

```promql
rate(srtm_cache_events_total{tier="disk",event="hit"}[5m])
```

cannot be broken down by DEM source, making it impossible to compare cache
efficiency between SRTM and alternative sources once they are enabled.

**Fix (in this PR):**
- `app/metrics.py:52`: added `"source"` to `labelnames`.
- `app/services/splat.py:859,868,874`: each call site now passes
  `source=self.dem_source`.

**Migration note:** the counter's label set is additive, not back-compatible.
Any existing Prometheus recording rule or dashboard that uses
`srtm_cache_events_total` without a `source` selector will match nothing after
the label is added — update selectors to include `source=~".+"` or a specific
source name.

**Current state (before this fix):** zero per-source ratio data available.
After the fix, ratios will be queryable via:

```promql
sum(rate(srtm_cache_events_total{tier=~"disk|redis",event="hit",source="srtm"}[1h]))
  /
sum(rate(srtm_cache_events_total{event=~"hit|miss",source="srtm"}[1h]))
```

---

## 2. Production rollout — no alternative source activated

Searched: `.env.example`, `docker-compose.yml`, `.github/`, git log since 2026-05-01.

| File | DEM_SOURCE default | CLUTTER_SOURCE default |
|------|-------------------|------------------------|
| `.env.example:60` | `srtm` | `none` |
| `docker-compose.yml:14` | `${DEM_SOURCE:-srtm}` | `${CLUTTER_SOURCE:-none}` |

**Finding:** Neither `DEM_SOURCE=copernicus` nor `DEM_SOURCE=fabdem` has been
activated in any tracked deployment configuration. No git commit since Phase
A/B/C merged (2026-05-01, commit `60ca150`) touches `DEM_SOURCE` in `.env.example`
or `docker-compose.yml`.

The FABDEM operational blocker remains open: `docs/dem-roadmap.md` Phase B still
has the "Hospedagem ainda pendente" checkbox unchecked — no operator mirror has
been announced or documented.

**Conclusion:** production is running `DEM_SOURCE=srtm` / `CLUTTER_SOURCE=none`.
The Phase A Copernicus path is code-complete and deployable today with zero
infrastructure work; it only needs `DEM_SOURCE=copernicus` set in `.env`.

---

## 3. Field RSSI / calibration data — none collected

Searched for: CSV/JSON data files, new docs, `rssi`/`calibrat`/`measurement`/
`ground-truth` references added since 2026-05-01.

**Finding:** The infrastructure (ORM model, CRUD router, offline solver) is all
present and functional:
- `app/models/calibration_measurement.py` — DB table schema ✅
- `app/routers/calibration.py` — `POST/GET /api/calibration/measurements` ✅
- `utils/calibrate_clutter.py` — factor grid-search solver ✅

But zero actual measurements exist in the repo (no fixture CSV, no DB dump, no
MQTT integration merged). `CLUTTER_FACTOR_CALIBRATED=false` is still the default
in `.env.example:89`.

The roadmap (`docs/dem-roadmap.md`, "Próximos passos") already sets the threshold:
> "Sem ≥ 30 medições, calibração estatística não faz sentido."

**Conclusion:** not enough data to propose a revised `CLUTTER_PENETRATION_FACTOR`.
The default of `0.6` remains a placeholder. No change to the default value in
this PR.

The `CLUTTER_PENETRATION_FACTOR` default lives at:
- `app/services/clutter.py:171` — `os.environ.get("CLUTTER_PENETRATION_FACTOR", "0.6")`
- `.env.example:85` — `CLUTTER_PENETRATION_FACTOR=0.6`

Both should be updated (with a comment linking to a calibration result) once a
corpus of ≥ 30 measurements is available and `calibrate_clutter.py` has been run.

---

## Summary

| Item | Status | Action |
|------|--------|--------|
| Per-source cache metric label | **Fixed** in this PR | Dashboard selectors need updating |
| Copernicus rollout | Not activated | Can enable today with `DEM_SOURCE=copernicus` — no infra work |
| FABDEM rollout | Blocked on mirror | Needs operator S3 bucket |
| Clutter activation | Not activated | Requires mirror + calibration first |
| Calibration data | **0 measurements** | Collect ≥ 30 before re-running review |
| `CLUTTER_PENETRATION_FACTOR` | 0.6 placeholder | Unchanged — no data to fit |
