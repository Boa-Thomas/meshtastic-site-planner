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

from app.redis_config import DB_CELERY_BACKEND, DB_CELERY_BROKER, redis_url

celery_app = Celery(
    "meshtastic_planner",
    broker=redis_url(DB_CELERY_BROKER),
    backend=redis_url(DB_CELERY_BACKEND),
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
