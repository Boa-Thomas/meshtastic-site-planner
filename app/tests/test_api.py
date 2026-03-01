"""
Tests for the FastAPI endpoints: POST /predict, GET /status/{task_id}, GET /result/{task_id}.

The httpx.AsyncClient fixture from conftest.py replaces:
  - redis_client  →  MockRedis (in-memory dict store)
  - splat_service →  MagicMock (returns fake GeoTIFF bytes)
"""

import uuid
import pytest
import asyncio

from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PREDICT_PAYLOAD = {
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


def run(coro):
    """Run a coroutine synchronously using a fresh event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# POST /predict
# ---------------------------------------------------------------------------


def test_predict_returns_task_id(client):
    """POST /predict with a valid payload must return a JSON body with a 'task_id' field."""
    http_client, mock_redis, mock_splat = client

    response = run(http_client.post("/predict", json=VALID_PREDICT_PAYLOAD))

    assert response.status_code == 200, response.text
    body = response.json()
    assert "task_id" in body, f"Missing 'task_id' in response: {body}"

    # Validate that the returned value is a valid UUID
    task_id = body["task_id"]
    parsed = uuid.UUID(task_id)  # raises ValueError if invalid
    assert str(parsed) == task_id


def test_predict_stores_processing_status_in_redis(client):
    """After POST /predict the status key must be set to 'processing' in Redis."""
    http_client, mock_redis, mock_splat = client

    response = run(http_client.post("/predict", json=VALID_PREDICT_PAYLOAD))
    assert response.status_code == 200

    task_id = response.json()["task_id"]
    status_bytes = mock_redis.get(f"{task_id}:status")
    assert status_bytes is not None, "Status key was not written to Redis"
    assert status_bytes.decode("utf-8") == "processing"


def test_predict_rejects_invalid_lat(client):
    """POST /predict with lat > 90 must return HTTP 422 Unprocessable Entity."""
    http_client, mock_redis, mock_splat = client

    payload = {**VALID_PREDICT_PAYLOAD, "lat": 91.0}
    response = run(http_client.post("/predict", json=payload))

    assert response.status_code == 422


def test_predict_rejects_invalid_lon(client):
    """POST /predict with lon > 180 must return HTTP 422 Unprocessable Entity."""
    http_client, mock_redis, mock_splat = client

    payload = {**VALID_PREDICT_PAYLOAD, "lon": 181.0}
    response = run(http_client.post("/predict", json=payload))

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /status/{task_id}
# ---------------------------------------------------------------------------


def test_get_status_returns_404_for_unknown_task(client):
    """GET /status/<random-uuid> must return HTTP 404 when the task does not exist."""
    http_client, mock_redis, mock_splat = client

    unknown_id = str(uuid.uuid4())
    response = run(http_client.get(f"/status/{unknown_id}"))

    assert response.status_code == 404, response.text
    body = response.json()
    assert "error" in body


def test_get_status_returns_processing_for_known_task(client):
    """GET /status/<task-id> must return the status stored in Redis."""
    http_client, mock_redis, mock_splat = client

    # Manually plant a task status in mock Redis
    task_id = str(uuid.uuid4())
    mock_redis.setex(f"{task_id}:status", 3600, "processing")

    response = run(http_client.get(f"/status/{task_id}"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["task_id"] == task_id


def test_get_status_returns_completed_status(client):
    """GET /status/<task-id> must return 'completed' when the task is done."""
    http_client, mock_redis, mock_splat = client

    task_id = str(uuid.uuid4())
    mock_redis.setex(f"{task_id}:status", 3600, "completed")

    response = run(http_client.get(f"/status/{task_id}"))

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# GET /result/{task_id}
# ---------------------------------------------------------------------------


def test_get_result_returns_404_for_unknown_task(client):
    """GET /result/<random-uuid> must return HTTP 404 when the task does not exist."""
    http_client, mock_redis, mock_splat = client

    unknown_id = str(uuid.uuid4())
    response = run(http_client.get(f"/result/{unknown_id}"))

    assert response.status_code == 404, response.text
    body = response.json()
    assert "error" in body


def test_get_result_returns_geotiff_for_completed_task(client):
    """GET /result/<task-id> must stream the GeoTIFF bytes for a completed task."""
    http_client, mock_redis, mock_splat = client

    task_id = str(uuid.uuid4())
    fake_geotiff = b"FAKE_GEOTIFF_DATA"
    mock_redis.setex(f"{task_id}:status", 3600, "completed")
    mock_redis.setex(task_id, 3600, fake_geotiff)

    response = run(http_client.get(f"/result/{task_id}"))

    assert response.status_code == 200
    assert response.content == fake_geotiff
    assert response.headers["content-type"] == "image/tiff"


def test_get_result_returns_processing_status(client):
    """GET /result/<task-id> must return JSON with status 'processing' when not yet done."""
    http_client, mock_redis, mock_splat = client

    task_id = str(uuid.uuid4())
    mock_redis.setex(f"{task_id}:status", 3600, "processing")

    response = run(http_client.get(f"/result/{task_id}"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"


def test_get_result_returns_failed_status_with_error(client):
    """GET /result/<task-id> must return status 'failed' and the error message."""
    http_client, mock_redis, mock_splat = client

    task_id = str(uuid.uuid4())
    mock_redis.setex(f"{task_id}:status", 3600, "failed")
    mock_redis.setex(f"{task_id}:error", 3600, "SPLAT! binary not found")

    response = run(http_client.get(f"/result/{task_id}"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert "error" in body
