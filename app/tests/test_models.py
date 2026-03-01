"""
Tests for the CoveragePredictionRequest Pydantic model.
"""

import pytest
from pydantic import ValidationError

from app.models.CoveragePredictionRequest import CoveragePredictionRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PAYLOAD: dict = {
    "lat": -23.5505,
    "lon": -46.6333,
    "tx_height": 10.0,
    "tx_power": 30.0,
    "tx_gain": 2.0,
    "frequency_mhz": 905.0,
    "rx_height": 2.0,
    "rx_gain": 1.0,
    "signal_threshold": -100.0,
    "clutter_height": 0.0,
    "radius": 5000.0,
    "polarization": "vertical",
    "radio_climate": "continental_temperate",
    "colormap": "rainbow",
    "min_dbm": -130.0,
    "max_dbm": -30.0,
}


# ---------------------------------------------------------------------------
# Valid data
# ---------------------------------------------------------------------------


def test_valid_payload_is_accepted():
    """CoveragePredictionRequest must accept a complete, valid payload."""
    req = CoveragePredictionRequest(**VALID_PAYLOAD)

    assert req.lat == pytest.approx(-23.5505)
    assert req.lon == pytest.approx(-46.6333)
    assert req.tx_power == pytest.approx(30.0)
    assert req.frequency_mhz == pytest.approx(905.0)
    assert req.polarization == "vertical"
    assert req.radio_climate == "continental_temperate"


# ---------------------------------------------------------------------------
# Latitude / Longitude validation
# ---------------------------------------------------------------------------


def test_invalid_lat_above_90_raises_validation_error():
    """Latitude > 90 must raise a ValidationError."""
    payload = {**VALID_PAYLOAD, "lat": 91.0}
    with pytest.raises(ValidationError) as exc_info:
        CoveragePredictionRequest(**payload)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("lat",) for e in errors), (
        f"Expected a 'lat' field error, got: {errors}"
    )


def test_invalid_lat_below_minus_90_raises_validation_error():
    """Latitude < -90 must raise a ValidationError."""
    payload = {**VALID_PAYLOAD, "lat": -91.0}
    with pytest.raises(ValidationError) as exc_info:
        CoveragePredictionRequest(**payload)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("lat",) for e in errors)


def test_invalid_lon_above_180_raises_validation_error():
    """Longitude > 180 must raise a ValidationError."""
    payload = {**VALID_PAYLOAD, "lon": 181.0}
    with pytest.raises(ValidationError) as exc_info:
        CoveragePredictionRequest(**payload)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("lon",) for e in errors), (
        f"Expected a 'lon' field error, got: {errors}"
    )


def test_invalid_lon_below_minus_180_raises_validation_error():
    """Longitude < -180 must raise a ValidationError."""
    payload = {**VALID_PAYLOAD, "lon": -181.0}
    with pytest.raises(ValidationError) as exc_info:
        CoveragePredictionRequest(**payload)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("lon",) for e in errors)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_tx_height_default_is_one():
    """tx_height must default to 1 when omitted."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "tx_height"}
    req = CoveragePredictionRequest(**payload)
    assert req.tx_height == pytest.approx(1.0)


def test_rx_height_default_is_one():
    """rx_height must default to 1 when omitted."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "rx_height"}
    req = CoveragePredictionRequest(**payload)
    assert req.rx_height == pytest.approx(1.0)


def test_frequency_mhz_default_is_905():
    """frequency_mhz must default to 905 MHz when omitted."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "frequency_mhz"}
    req = CoveragePredictionRequest(**payload)
    assert req.frequency_mhz == pytest.approx(905.0)


def test_radio_climate_default_is_continental_temperate():
    """radio_climate must default to 'continental_temperate' when omitted."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "radio_climate"}
    req = CoveragePredictionRequest(**payload)
    assert req.radio_climate == "continental_temperate"


def test_polarization_default_is_vertical():
    """polarization must default to 'vertical' when omitted."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "polarization"}
    req = CoveragePredictionRequest(**payload)
    assert req.polarization == "vertical"


def test_high_resolution_default_is_false():
    """high_resolution must default to False when omitted."""
    req = CoveragePredictionRequest(**VALID_PAYLOAD)
    assert req.high_resolution is False


def test_signal_threshold_default_is_minus_100():
    """signal_threshold must default to -100 when omitted."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "signal_threshold"}
    req = CoveragePredictionRequest(**payload)
    assert req.signal_threshold == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# Other field constraints
# ---------------------------------------------------------------------------


def test_tx_power_must_be_positive():
    """tx_power <= 0 must raise a ValidationError (field is gt=0)."""
    payload = {**VALID_PAYLOAD, "tx_power": 0.0}
    with pytest.raises(ValidationError) as exc_info:
        CoveragePredictionRequest(**payload)

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("tx_power",) for e in errors)


def test_invalid_polarization_raises_validation_error():
    """An unknown polarization value must raise a ValidationError."""
    payload = {**VALID_PAYLOAD, "polarization": "circular"}
    with pytest.raises(ValidationError):
        CoveragePredictionRequest(**payload)


def test_invalid_radio_climate_raises_validation_error():
    """An unknown radio_climate value must raise a ValidationError."""
    payload = {**VALID_PAYLOAD, "radio_climate": "arctic"}
    with pytest.raises(ValidationError):
        CoveragePredictionRequest(**payload)
