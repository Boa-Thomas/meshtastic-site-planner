"""
Tile prefetch worker (Phase 3.2 of the performance plan).

Reads the popularity ranking maintained in Redis ZSET ``srtm:access`` and
makes sure the top-N most-frequently-used tiles are warm in the Redis cache
(``srtm:hgt:*``). Eliminates cold-start S3 latency for hot regions.

Usage as a standalone process (e.g. inside docker-compose):

    python -m app.prefetch [--top-n 50] [--interval 300] [--once]

Environment variables:
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD - shared with the rest of the app
    SPLAT_PATH                              - SPLAT! binary directory
    PREFETCH_TOP_N                          - default top-N (defaults to 50)
    PREFETCH_INTERVAL_SECONDS               - sleep between cycles (300)
    PREFETCH_MIN_HITS                       - skip tiles with fewer hits (default 2)

Designed to be safe to run alongside live workers; it only writes to the
Redis HGT cache (DB 3) and never mutates application state.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Iterable

from app.redis_config import DB_SRTM_CACHE, get_redis_client

logger = logging.getLogger("prefetch")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s prefetch: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_engine():
    """Lazily import and instantiate the Splat engine."""
    from app.services.engine_factory import get_engine
    return get_engine("splat")


def _top_tiles(redis_client, top_n: int, min_hits: int) -> list[tuple[str, float]]:
    """Return [(tile_name, score)] sorted by access count desc."""
    raw = redis_client.zrevrange("srtm:access", 0, top_n - 1, withscores=True)
    out: list[tuple[str, float]] = []
    for entry, score in raw:
        if score < min_hits:
            continue
        name = entry.decode("utf-8") if isinstance(entry, bytes) else entry
        out.append((name, float(score)))
    return out


def _ensure_cached(engine, redis_client, tiles: Iterable[tuple[str, float]]) -> tuple[int, int]:
    """For each tile, fetch via the engine if it's not already in the Redis cache.

    Returns (warmed_count, already_cached_count).
    """
    warmed = 0
    already = 0
    for tile_name, _ in tiles:
        redis_key = f"srtm:hgt:{tile_name}"
        try:
            if redis_client.exists(redis_key):
                already += 1
                continue
            # _download_terrain_tile is internally idempotent and writes to
            # both the disk LRU and Redis (via _cache_tile).
            engine._download_terrain_tile(tile_name)
            warmed += 1
            logger.info(f"warmed {tile_name}")
        except Exception as e:
            logger.warning(f"failed to warm {tile_name}: {e}")
    return warmed, already


def run_once(top_n: int, min_hits: int) -> None:
    redis_client = get_redis_client(db=DB_SRTM_CACHE)
    tiles = _top_tiles(redis_client, top_n=top_n, min_hits=min_hits)
    if not tiles:
        logger.info("no popular tiles to prefetch yet")
        return
    engine = _build_engine()
    warmed, already = _ensure_cached(engine, redis_client, tiles)
    logger.info(f"cycle complete: warmed={warmed} already_cached={already} considered={len(tiles)}")


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--top-n",
        type=int,
        default=int(os.environ.get("PREFETCH_TOP_N", "50")),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("PREFETCH_INTERVAL_SECONDS", "300")),
        help="seconds between cycles (ignored when --once is given)",
    )
    parser.add_argument(
        "--min-hits",
        type=int,
        default=int(os.environ.get("PREFETCH_MIN_HITS", "2")),
        help="skip tiles with fewer than this many recorded accesses",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run a single cycle and exit (handy for cron / one-shot tests)",
    )
    args = parser.parse_args()

    if args.once:
        run_once(args.top_n, args.min_hits)
        return

    logger.info(
        f"starting prefetch loop: top_n={args.top_n} min_hits={args.min_hits} "
        f"interval={args.interval}s"
    )
    while True:
        try:
            run_once(args.top_n, args.min_hits)
        except Exception as e:
            logger.error(f"unexpected error in prefetch cycle: {e}")
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
