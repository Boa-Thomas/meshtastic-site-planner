"""Pure-logic tests for utils/calibrate_clutter.py — no real /predict runs."""

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def calib_module():
    path = REPO_ROOT / "utils" / "calibrate_clutter.py"
    spec = importlib.util.spec_from_file_location("calibrate_clutter", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["calibrate_clutter"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# pixel_to_dbm — SPLAT! grayscale inverse
# ---------------------------------------------------------------------------


class TestPixelToDbm:
    def test_nodata_returns_none(self, calib_module):
        assert calib_module.pixel_to_dbm(255) is None

    def test_high_pixel_strong_signal(self, calib_module):
        # Pixel 247 ↔ -30 dBm (top of SPLAT! grayscale ramp).
        assert calib_module.pixel_to_dbm(247) == pytest.approx(-30, abs=0.5)

    def test_zero_pixel_weak_signal(self, calib_module):
        assert calib_module.pixel_to_dbm(0) == pytest.approx(-130, abs=0.5)

    def test_midpoint(self, calib_module):
        # ~midway should be close to -80 dBm.
        midpoint = calib_module.pixel_to_dbm(124)
        assert midpoint == pytest.approx(-80, abs=2)

    def test_out_of_range_returns_none(self, calib_module):
        assert calib_module.pixel_to_dbm(-1) is None
        assert calib_module.pixel_to_dbm(248) is None


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


class TestSummarise:
    def test_picks_lowest_mae(self, calib_module):
        runs = [
            calib_module.CandidateRun(measurement_id=1, factor=0.4, predicted_dbm=-90, error_db=-5),
            calib_module.CandidateRun(measurement_id=2, factor=0.4, predicted_dbm=-91, error_db=-6),
            calib_module.CandidateRun(measurement_id=1, factor=0.6, predicted_dbm=-86, error_db=-1),
            calib_module.CandidateRun(measurement_id=2, factor=0.6, predicted_dbm=-87, error_db=-2),
        ]
        summary = calib_module.summarise(runs)
        assert summary["best"]["factor"] == 0.6
        assert summary["best"]["mae_db"] == 1.5

    def test_skips_runs_without_error(self, calib_module):
        runs = [
            calib_module.CandidateRun(measurement_id=1, factor=0.5, predicted_dbm=None, error_db=None, notes="task failed"),
            calib_module.CandidateRun(measurement_id=2, factor=0.5, predicted_dbm=-90, error_db=-3),
        ]
        summary = calib_module.summarise(runs)
        assert summary["per_factor"][0]["samples"] == 1

    def test_empty(self, calib_module):
        summary = calib_module.summarise([])
        assert summary["best"] is None
        assert summary["per_factor"] == []


# ---------------------------------------------------------------------------
# build_predict_payload
# ---------------------------------------------------------------------------


class TestBuildPredictPayload:
    def test_passes_through_overrides(self, calib_module):
        measurement = {
            "id": 1,
            "txLat": -23.5, "txLon": -46.5,
            "rxLat": -23.6, "rxLon": -46.6,
            "txHeightM": 2.0, "txPowerDbm": 20.0, "txGainDbi": 3.0,
            "frequencyMhz": 915.0,
            "rxHeightM": 1.5, "rxGainDbi": 2.0, "rxLossDb": 1.0,
            "rssiDbm": -95.0,
        }
        payload = calib_module.build_predict_payload(
            measurement, factor=0.55,
            radius_m=10000, dem_source="fabdem", clutter_source="lang2023",
        )
        assert payload["dem_source"] == "fabdem"
        assert payload["clutter_source"] == "lang2023"
        assert payload["clutter_penetration_factor"] == 0.55
        assert payload["lat"] == -23.5
        assert payload["radius"] == 10000

    def test_minimum_heights_clamped(self, calib_module):
        # SPLAT! requires tx_height >= 1; the script must clamp from 0.0
        # measurements to avoid pydantic validation errors at the API.
        measurement = {
            "id": 1,
            "txLat": 0, "txLon": 0, "rxLat": 0, "rxLon": 0,
            "txHeightM": 0.5, "txPowerDbm": 20, "txGainDbi": 0,
            "frequencyMhz": 915,
            "rxHeightM": 0.0, "rxGainDbi": 0, "rxLossDb": 0,
            "rssiDbm": -100,
        }
        payload = calib_module.build_predict_payload(
            measurement, factor=0.6,
            radius_m=1000, dem_source=None, clutter_source="none",
        )
        assert payload["tx_height"] == 1.0
        assert payload["rx_height"] == 1.0


# ---------------------------------------------------------------------------
# haversine
# ---------------------------------------------------------------------------


class TestHaversine:
    def test_zero_distance(self, calib_module):
        assert calib_module.haversine_m(0, 0, 0, 0) == 0

    def test_known_short_distance(self, calib_module):
        # Roughly 1° lat at the equator ≈ 111 km.
        d = calib_module.haversine_m(0, 0, 1, 0)
        assert 110_000 < d < 112_000
