"""
Pytest configuration and shared fixtures for the Meshtastic Site Planner test suite.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from typing import Generator, Tuple

from httpx import AsyncClient, ASGITransport


class MockRedis:
    """
    Simple dict-based Redis mock that covers the subset of redis.StrictRedis
    used by app/main.py: setex, get, delete.
    """

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def setex(self, key: str, ttl: int, value) -> None:
        if isinstance(value, str):
            value = value.encode("utf-8")
        self._store[str(key)] = value

    def get(self, key: str):
        return self._store.get(str(key))

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if str(key) in self._store:
                del self._store[str(key)]
                deleted += 1
        return deleted

    def clear(self) -> None:
        self._store.clear()


@pytest.fixture
def mock_redis() -> MockRedis:
    """Provide a fresh MockRedis instance for each test."""
    return MockRedis()


@pytest.fixture
def mock_splat() -> MagicMock:
    """Provide a MagicMock for the Splat service."""
    splat = MagicMock()
    splat.coverage_prediction.return_value = b"FAKE_GEOTIFF_DATA"
    return splat


@pytest.fixture
def client(
    mock_redis: MockRedis,
    mock_splat: MagicMock,
) -> Generator[Tuple[AsyncClient, MockRedis, MagicMock], None, None]:
    """
    Yield a 3-tuple of (http_client, mock_redis, mock_splat).

    The httpx.AsyncClient is wired to the FastAPI app via ASGITransport.
    Both the Redis client and the Splat service are replaced with lightweight
    mocks so tests run without real infrastructure.

    Usage in tests::

        def test_something(client):
            http_client, mock_redis, mock_splat = client
            response = run(http_client.get("/status/some-id"))
    """
    with (
        patch("app.main.redis_client", mock_redis),
        patch("app.main.splat_service", mock_splat),
    ):
        from app.main import app  # noqa: PLC0415

        transport = ASGITransport(app=app)
        loop = asyncio.new_event_loop()
        try:
            http_client = loop.run_until_complete(
                AsyncClient(transport=transport, base_url="http://test").__aenter__()
            )
            yield http_client, mock_redis, mock_splat
        finally:
            loop.run_until_complete(http_client.__aexit__(None, None, None))
            loop.close()
