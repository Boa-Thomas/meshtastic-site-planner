"""Debug status API endpoint for monitoring workers and queues."""

import json
import logging
import time
from fastapi import APIRouter

from app.redis_config import DB_APP, DB_CELERY_BROKER, get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _get_queue_depths() -> dict:
    """Get Celery queue depths from Redis broker (DB 1)."""
    try:
        r = get_redis_client(db=DB_CELERY_BROKER, decode_responses=True)
        return {
            "default": r.llen("default") or 0,
            "heavy": r.llen("heavy") or 0,
        }
    except Exception as e:
        logger.warning(f"Failed to read queue depths: {e}")
        return {"default": -1, "heavy": -1}


def _get_active_tasks() -> list:
    """Scan Redis DB 0 for tasks with status 'processing' and their progress."""
    try:
        r = get_redis_client(db=DB_APP, decode_responses=True)
        active = []
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match="*:status", count=100)
            for key in keys:
                status = r.get(key)
                if status == "processing":
                    task_id = key.rsplit(":status", 1)[0]
                    task_info = {"task_id": task_id}
                    progress_raw = r.get(f"{task_id}:progress")
                    if progress_raw:
                        try:
                            task_info["progress"] = json.loads(progress_raw)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    active.append(task_info)
            if cursor == 0:
                break
        return active
    except Exception as e:
        logger.warning(f"Failed to scan active tasks: {e}")
        return []


def _get_worker_counts() -> dict:
    """Get active worker counts via Celery inspect."""
    try:
        from app.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        active_queues = inspect.active_queues() or {}

        light = 0
        heavy = 0
        for worker_name, queues in active_queues.items():
            queue_names = {q["name"] for q in queues}
            if "heavy" in queue_names:
                heavy += 1
            else:
                light += 1

        return {"light": light, "heavy": heavy}
    except Exception as e:
        logger.warning(f"Failed to inspect workers: {e}")
        return {"light": -1, "heavy": -1}


@router.get("/status")
def debug_status():
    """Return current system status: queues, workers, active tasks, config."""
    return {
        "queues": _get_queue_depths(),
        "active_tasks": _get_active_tasks(),
        "workers": _get_worker_counts(),
        "config": {
            "max_light": int(os.environ.get("MAX_LIGHT_WORKERS", "6")),
            "max_heavy": int(os.environ.get("MAX_HEAVY_WORKERS", "4")),
            "heavy_threshold_km": int(os.environ.get("HEAVY_RADIUS_THRESHOLD_KM", "200")),
        },
        "timestamp": int(time.time()),
    }
