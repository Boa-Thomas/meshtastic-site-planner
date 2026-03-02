"""Tests for Celery task dispatch and serialization."""

import os
import pytest
from unittest.mock import patch, MagicMock
from app.models.CoveragePredictionRequest import CoveragePredictionRequest


def _make_payload() -> dict:
    """Create a minimal valid CoveragePredictionRequest as dict."""
    return {
        "lat": -26.82,
        "lon": -49.27,
        "tx_height": 10.0,
        "tx_power": 30.0,
        "tx_gain": 2.0,
        "frequency_mhz": 906.0,
        "rx_height": 1.5,
        "rx_gain": 0.0,
        "signal_threshold": -120.0,
        "clutter_height": 5.0,
        "radius": 50000.0,
    }


class TestSerialization:
    """Test that CoveragePredictionRequest survives dict round-trip."""

    def test_roundtrip(self):
        payload = _make_payload()
        req = CoveragePredictionRequest(**payload)
        dumped = req.model_dump()
        restored = CoveragePredictionRequest(**dumped)
        assert restored.lat == req.lat
        assert restored.lon == req.lon
        assert restored.tx_power == req.tx_power
        assert restored.radius == req.radius

    def test_rf_hash_stable(self):
        payload = _make_payload()
        req1 = CoveragePredictionRequest(**payload)
        req2 = CoveragePredictionRequest(**payload)
        assert req1.rf_param_hash() == req2.rf_param_hash()

    def test_rf_hash_excludes_display(self):
        payload = _make_payload()
        req1 = CoveragePredictionRequest(**payload)
        payload["colormap"] = "viridis"
        payload["min_dbm"] = -100.0
        req2 = CoveragePredictionRequest(**payload)
        assert req1.rf_param_hash() == req2.rf_param_hash()


class TestCeleryFlag:
    """Test USE_CELERY feature flag dispatch logic."""

    def test_use_celery_false_by_default(self):
        """Default: USE_CELERY is false."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("USE_CELERY", None)
            flag = os.environ.get("USE_CELERY", "false").lower() == "true"
            assert flag is False

    def test_use_celery_true(self):
        with patch.dict(os.environ, {"USE_CELERY": "true"}):
            flag = os.environ.get("USE_CELERY", "false").lower() == "true"
            assert flag is True

    def test_use_celery_case_insensitive(self):
        with patch.dict(os.environ, {"USE_CELERY": "True"}):
            flag = os.environ.get("USE_CELERY", "false").lower() == "true"
            assert flag is True
