"""
Offline calibration solver for ``CLUTTER_PENETRATION_FACTOR``.

Default 0.6 is a placeholder. This script loads ground-truth RSSI measurements
from `/api/calibration/measurements`, runs the SPLAT! pipeline against each
measurement at several candidate penetration factors, and fits the factor that
minimises the prediction error.

Workflow:

1. Fetch measurements from the API (filter by DEM/clutter source if needed).
2. For each (measurement × candidate factor):
   a. POST to /predict with the measurement's RF params + the candidate factor.
   b. Wait for the task to complete and download the GeoTIFF.
   c. Sample the predicted RSSI at the measurement's RX coord.
3. Compute mean absolute error (MAE) per candidate factor.
4. Report the best factor along with per-measurement residuals.

Cost note: each (measurement × factor) is one full SPLAT! run. With N
measurements and K factors that's N*K simulations. The script writes a
JSON cache so re-runs only fetch new combinations.

Example
-------

    python utils/calibrate_clutter.py \\
        --api-base http://localhost:8080 \\
        --clutter-source lang2023 \\
        --dem-source fabdem \\
        --factors 0.3,0.4,0.5,0.6,0.7,0.8 \\
        --output calibration-result.json

The result JSON tells the operator what to put in ``CLUTTER_PENETRATION_FACTOR``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import os
import sys
import time
from typing import Iterable, Optional

logger = logging.getLogger("calibrate_clutter")

# SPLAT!'s grayscale dcf maps pixel value 247 → -30 dBm, pixel 0 → -130 dBm,
# pixel 255 → nodata. We invert that here for dBm extraction.
SPLAT_DBM_HIGH = -30.0
SPLAT_DBM_LOW = -130.0
SPLAT_GRAY_HIGH = 247  # corresponds to SPLAT_DBM_HIGH
SPLAT_NODATA_PIXEL = 255


@dataclasses.dataclass
class CandidateRun:
    measurement_id: int
    factor: float
    task_id: Optional[str] = None
    predicted_dbm: Optional[float] = None
    error_db: Optional[float] = None
    notes: Optional[str] = None


def pixel_to_dbm(pixel: int) -> Optional[float]:
    """Invert SPLAT!'s grayscale dBm encoding. Returns None for nodata."""
    if pixel == SPLAT_NODATA_PIXEL:
        return None
    if pixel < 0 or pixel > SPLAT_GRAY_HIGH:
        return None
    # Linear ramp: pixel 0 ↔ -130 dBm, pixel 247 ↔ -30 dBm.
    return SPLAT_DBM_LOW + (pixel / SPLAT_GRAY_HIGH) * (SPLAT_DBM_HIGH - SPLAT_DBM_LOW)


def sample_geotiff(geotiff_bytes: bytes, lat: float, lon: float) -> Optional[float]:
    """Read a GeoTIFF and return the predicted dBm at the given coord."""
    import rasterio  # type: ignore
    with rasterio.MemoryFile(geotiff_bytes) as memfile:
        with memfile.open() as src:
            try:
                row, col = src.index(lon, lat)
            except Exception:
                return None
            if row < 0 or col < 0 or row >= src.height or col >= src.width:
                return None
            window = rasterio.windows.Window(col_off=col, row_off=row, width=1, height=1)
            arr = src.read(1, window=window)
            if arr.size == 0:
                return None
            return pixel_to_dbm(int(arr.flat[0]))


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class CalibrationApi:
    def __init__(self, base_url: str, timeout: float = 60.0):
        import requests  # type: ignore
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.timeout = timeout

    def list_measurements(
        self,
        dem_source: Optional[str] = None,
        clutter_source: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict]:
        params = {"limit": limit}
        if dem_source:
            params["dem_source"] = dem_source
        if clutter_source:
            params["clutter_source"] = clutter_source
        resp = self.session.get(
            f"{self.base_url}/api/calibration/measurements",
            params=params, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("items", [])

    def submit_prediction(self, payload: dict) -> str:
        resp = self.session.post(
            f"{self.base_url}/predict", json=payload, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()["task_id"]

    def wait_for_task(self, task_id: str, poll_interval: float = 2.0,
                      max_wait: float = 600.0) -> bool:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            resp = self.session.get(
                f"{self.base_url}/status/{task_id}", timeout=self.timeout,
            )
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            status = resp.json().get("status")
            if status == "completed":
                return True
            if status == "failed":
                return False
            time.sleep(poll_interval)
        return False

    def fetch_result(self, task_id: str) -> bytes:
        resp = self.session.get(
            f"{self.base_url}/result/{task_id}", timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.content


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------


def build_predict_payload(measurement: dict, factor: float, *,
                          radius_m: int, dem_source: Optional[str],
                          clutter_source: str) -> dict:
    """Translate a measurement row + factor into a /predict request body."""
    return {
        "lat": measurement["txLat"],
        "lon": measurement["txLon"],
        "tx_height": max(measurement["txHeightM"], 1.0),
        "tx_power": measurement["txPowerDbm"],
        "tx_gain": measurement["txGainDbi"],
        "frequency_mhz": measurement["frequencyMhz"],
        "rx_height": max(measurement["rxHeightM"], 1.0),
        "rx_gain": measurement["rxGainDbi"],
        # Use a permissive threshold so weak measurements don't fall into nodata.
        "signal_threshold": -150,
        "system_loss": measurement.get("rxLossDb", 0.0),
        "clutter_height": 0,  # Use spatial clutter only — no extra uniform fudge.
        "ground_dielectric": 15.0,
        "ground_conductivity": 0.005,
        "atmosphere_bending": 301.0,
        "radius": radius_m,
        "situation_fraction": 50,
        "time_fraction": 90,
        "high_resolution": True,
        "dem_source": dem_source,
        "clutter_source": clutter_source,
        "clutter_penetration_factor": factor,
    }


def calibrate(
    api: CalibrationApi,
    measurements: list[dict],
    factors: list[float],
    *,
    dem_source: Optional[str],
    clutter_source: str,
    radius_m: int,
    cache_path: Optional[str],
) -> list[CandidateRun]:
    """Run the prediction grid and return per-(measurement, factor) results."""
    cache: dict[str, dict] = {}
    if cache_path and os.path.isfile(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)

    runs: list[CandidateRun] = []
    for m in measurements:
        radius_to_rx = haversine_m(m["txLat"], m["txLon"], m["rxLat"], m["rxLon"])
        if radius_to_rx > radius_m:
            logger.warning(
                f"measurement {m['id']}: rx is {radius_to_rx:.0f} m from tx, "
                f"but --radius-m={radius_m}; skipping"
            )
            continue
        for factor in factors:
            cache_key = f"{m['id']}:{factor:.3f}:{dem_source or 'default'}:{clutter_source}"
            run = CandidateRun(measurement_id=m["id"], factor=factor)

            if cache_key in cache:
                run.predicted_dbm = cache[cache_key].get("predicted_dbm")
                run.task_id = cache[cache_key].get("task_id")
                run.notes = "cached"
            else:
                payload = build_predict_payload(
                    m, factor,
                    radius_m=radius_m,
                    dem_source=dem_source,
                    clutter_source=clutter_source,
                )
                try:
                    run.task_id = api.submit_prediction(payload)
                    if not api.wait_for_task(run.task_id):
                        run.notes = "task did not complete"
                        runs.append(run)
                        continue
                    geotiff_bytes = api.fetch_result(run.task_id)
                    run.predicted_dbm = sample_geotiff(
                        geotiff_bytes, m["rxLat"], m["rxLon"],
                    )
                except Exception as e:
                    run.notes = f"error: {e}"
                    runs.append(run)
                    continue
                cache[cache_key] = {
                    "task_id": run.task_id,
                    "predicted_dbm": run.predicted_dbm,
                }
                if cache_path:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(cache, f, indent=2)

            if run.predicted_dbm is not None:
                run.error_db = run.predicted_dbm - m["rssiDbm"]
            runs.append(run)
            logger.info(
                f"measurement={m['id']} factor={factor:.2f} "
                f"predicted={run.predicted_dbm} measured={m['rssiDbm']} "
                f"error={run.error_db}"
            )
    return runs


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def summarise(runs: list[CandidateRun]) -> dict:
    """Produce a per-factor summary of mean error / RMSE / sample count."""
    by_factor: dict[float, list[CandidateRun]] = {}
    for r in runs:
        if r.error_db is None:
            continue
        by_factor.setdefault(r.factor, []).append(r)

    summary = []
    best = None
    for factor, group in sorted(by_factor.items()):
        errs = [r.error_db for r in group if r.error_db is not None]
        if not errs:
            continue
        mae = sum(abs(e) for e in errs) / len(errs)
        rmse = math.sqrt(sum(e * e for e in errs) / len(errs))
        bias = sum(errs) / len(errs)
        summary.append({
            "factor": factor,
            "samples": len(errs),
            "mae_db": round(mae, 2),
            "rmse_db": round(rmse, 2),
            "bias_db": round(bias, 2),
        })
        if best is None or mae < best["mae_db"]:
            best = {"factor": factor, "mae_db": round(mae, 2), "rmse_db": round(rmse, 2)}

    return {"per_factor": summary, "best": best}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_factors(value: str) -> list[float]:
    factors = []
    for part in value.split(","):
        f = float(part.strip())
        if not 0.0 <= f <= 1.0:
            raise argparse.ArgumentTypeError(f"factor {f} out of [0, 1]")
        factors.append(f)
    if not factors:
        raise argparse.ArgumentTypeError("at least one factor required")
    return factors


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-base", default=os.environ.get("CALIBRATION_API_BASE", "http://localhost:8080"))
    parser.add_argument("--dem-source", default=None,
                        help="Filter measurements + use this DEM in /predict")
    parser.add_argument("--clutter-source", required=True,
                        help="Clutter source to evaluate (e.g. lang2023, mapbiomas)")
    parser.add_argument("--factors", type=parse_factors,
                        default=parse_factors("0.3,0.4,0.5,0.6,0.7,0.8"),
                        help="Comma-separated list of penetration factors to try")
    parser.add_argument("--radius-m", type=int, default=15_000,
                        help="Simulation radius in meters (default 15000)")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Maximum number of measurements to use")
    parser.add_argument("--cache", default="calibration-cache.json",
                        help="Local file used to skip already-completed runs")
    parser.add_argument("--output", default="calibration-result.json",
                        help="Where to write the summary JSON")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")

    api = CalibrationApi(args.api_base)
    measurements = api.list_measurements(
        dem_source=args.dem_source,
        clutter_source=args.clutter_source,
        limit=args.limit,
    )
    if not measurements:
        logger.error("no calibration measurements found — collect some via "
                     "POST /api/calibration/measurements first")
        return 2
    logger.info(f"loaded {len(measurements)} measurements")

    runs = calibrate(
        api, measurements, args.factors,
        dem_source=args.dem_source,
        clutter_source=args.clutter_source,
        radius_m=args.radius_m,
        cache_path=args.cache,
    )
    summary = summarise(runs)
    summary["measurements_used"] = len(measurements)
    summary["dem_source"] = args.dem_source
    summary["clutter_source"] = args.clutter_source
    summary["factors_tried"] = args.factors

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({
            "summary": summary,
            "runs": [dataclasses.asdict(r) for r in runs],
        }, f, indent=2)

    print(json.dumps(summary, indent=2))
    if summary["best"]:
        logger.info(
            f"recommended CLUTTER_PENETRATION_FACTOR={summary['best']['factor']} "
            f"(MAE={summary['best']['mae_db']} dB)"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
