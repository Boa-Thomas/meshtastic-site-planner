"""
Celery application configuration.

Broker: Redis DB 1 (separate from app DB 0)
Backend: Redis DB 2

Queues:
  - default: lightweight simulations (radius <= HEAVY_RADIUS_THRESHOLD_KM)
  - heavy: large-area simulations (radius > HEAVY_RADIUS_THRESHOLD_KM)
"""

import os
from celery import Celery
from kombu import Queue

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

celery_app = Celery(
    "meshtastic_planner",
    broker=f"redis://{REDIS_HOST}:{REDIS_PORT}/1",
    backend=f"redis://{REDIS_HOST}:{REDIS_PORT}/2",
)

celery_app.conf.update(
    worker_concurrency=int(os.environ.get("CELERY_CONCURRENCY", "1")),
    worker_prefetch_multiplier=1,       # Fetch one task at a time
    task_acks_late=True,                # Ack after completion (enables retry on crash)
    task_time_limit=1800,               # 30 min hard limit
    task_soft_time_limit=1500,          # 25 min soft limit
    task_reject_on_worker_lost=True,    # Requeue on worker crash
    result_expires=3600,                # Results expire after 1 hour
    worker_max_tasks_per_child=10,      # Recycle worker after 10 tasks (memory cleanup)
    task_queues=[
        Queue("default"),
        Queue("heavy"),
    ],
    task_default_queue="default",
)
