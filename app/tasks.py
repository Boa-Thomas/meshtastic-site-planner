"""
Celery tasks for SPLAT! coverage prediction.

Workers create Splat and Redis instances lazily after fork
to avoid sharing connections across processes.
"""

import json
import logging
import os
from app.celery_app import celery_app
from app.models.CoveragePredictionRequest import CoveragePredictionRequest
from app.redis_config import get_redis_client

logger = logging.getLogger(__name__)

# Lazy-initialized singleton (created after Celery worker fork)
_redis_client = None


def _get_engine_for_request(request):
    from app.services.engine_factory import get_engine_for_request
    return get_engine_for_request(request)


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = get_redis_client()
        logger.info("Initialized Redis client (db=0) via redis_config")
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
        engine = _get_engine_for_request(request)
        geotiff_data = engine.coverage_prediction(request, task_id=task_id)

        r.setex(task_id, 3600, geotiff_data)
        r.setex(f"{task_id}:status", 3600, "completed")
        logger.info(f"[Celery] Task {task_id} completed successfully")

        # Persist to disk and database for long-term storage (survives Redis TTL expiry)
        try:
            from app.database import SessionLocal, RASTER_DIR
            from app.models.coverage_site import CoverageSite
            os.makedirs(RASTER_DIR, exist_ok=True)
            raster_path = os.path.join(RASTER_DIR, f"{task_id}.tif")
            with open(raster_path, "wb") as f:
                f.write(geotiff_data)
            db = SessionLocal()
            try:
                existing = db.query(CoverageSite).filter(CoverageSite.task_id == task_id).first()
                if not existing:
                    site = CoverageSite(
                        task_id=task_id,
                        params=json.dumps(request_dict),
                        raster_path=raster_path,
                    )
                    db.add(site)
                    db.commit()
            finally:
                db.close()
            logger.info(f"[Celery] Task {task_id} persisted to disk at {raster_path}")
        except Exception as persist_err:
            logger.warning(f"[Celery] Failed to persist task {task_id} to disk: {persist_err}")
    except Exception as e:
        logger.error(f"[Celery] Task {task_id} failed: {e}")
        r.setex(f"{task_id}:status", 3600, "failed")
        r.setex(f"{task_id}:error", 3600, str(e))
        raise
