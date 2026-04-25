"""
Centralized Redis configuration helpers.

Reads REDIS_HOST, REDIS_PORT, and REDIS_PASSWORD from the environment so all
modules connect with the same credentials. REDIS_PASSWORD is optional: when
unset, clients connect without authentication (backward compatible).

Database conventions:
  DB 0 — application data (task status, progress, results, RF dedup hash)
  DB 1 — Celery broker queues
  DB 2 — Celery result backend
  DB 3 — SRTM HGT tile cache (Phase 1.1)
"""

import os
from typing import Optional

import redis


REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD: Optional[str] = os.environ.get("REDIS_PASSWORD") or None

DB_APP = 0
DB_CELERY_BROKER = 1
DB_CELERY_BACKEND = 2
DB_SRTM_CACHE = 3


def redis_url(db: int = DB_APP) -> str:
    """Build a redis:// URL for Celery and other URL-based consumers."""
    auth = f":{REDIS_PASSWORD}@" if REDIS_PASSWORD else ""
    return f"redis://{auth}{REDIS_HOST}:{REDIS_PORT}/{db}"


def get_redis_client(db: int = DB_APP, decode_responses: bool = False) -> redis.StrictRedis:
    """Return a StrictRedis client wired to the configured host/port/password."""
    return redis.StrictRedis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=db,
        password=REDIS_PASSWORD,
        decode_responses=decode_responses,
    )
