"""
Celery tasks for SPLAT! coverage prediction.

Workers create Splat and Redis instances lazily after fork
to avoid sharing connections across processes.
"""

import logging
import redis
from app.celery_app import celery_app
from app.models.CoveragePredictionRequest import CoveragePredictionRequest

logger = logging.getLogger(__name__)

# Lazy-initialized singleton (created after Celery worker fork)
_redis_client = None


def _get_engine(name=None):
    from app.services.engine_factory import get_engine
    return get_engine(name)


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import os
        host = os.environ.get("REDIS_HOST", "redis")
        port = int(os.environ.get("REDIS_PORT", 6379))
        _redis_client = redis.StrictRedis(host=host, port=port, decode_responses=False)
        logger.info(f"Initialized Redis client (host={host}, port={port}, db=0)")
    return _redis_client


@celery_app.task(bind=True, max_retries=2, autoretry_for=(RuntimeError,), retry_backoff=True)
def run_splat_task(self, task_id: str, request_dict: dict):
    """
    Execute SPLAT! coverage prediction as a Celery task.

    Writes results to the same Redis keys (DB 0) used by the FastAPI app:
      - {task_id}:status  -> "completed" | "failed"
      - {task_id}        -> GeoTIFF bytes
      - {task_id}:error  -> error message (on failure)
    """
    r = _get_redis()

    try:
        logger.info(f"[Celery] Starting coverage prediction for task {task_id} (attempt {self.request.retries + 1})")
        request = CoveragePredictionRequest(**request_dict)
        engine = _get_engine(request.engine)
        geotiff_data = engine.coverage_prediction(request)

        r.setex(task_id, 3600, geotiff_data)
        r.setex(f"{task_id}:status", 3600, "completed")
        logger.info(f"[Celery] Task {task_id} completed successfully")
    except Exception as e:
        logger.error(f"[Celery] Task {task_id} failed: {e}")
        r.setex(f"{task_id}:status", 3600, "failed")
        r.setex(f"{task_id}:error", 3600, str(e))
        raise
