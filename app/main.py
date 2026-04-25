"""
Signal Coverage Prediction API

Provides endpoints to predict radio signal coverage
using the ITM (Irregular Terrain Model) via SPLAT! (https://github.com/jmcmellen/splat).

Endpoints:
    - /predict: Accepts a signal coverage prediction request and starts a background task.
    - /status/{task_id}: Retrieves the status of a given prediction task.
    - /result/{task_id}: Retrieves the result (GeoTIFF file) of a given prediction task.
"""

import asyncio
import json
import os
from fastapi import FastAPI, BackgroundTasks
from app.redis_config import get_redis_client
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from uuid import uuid4, UUID
from starlette.requests import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.services.engine_factory import get_engine
from app.models.CoveragePredictionRequest import CoveragePredictionRequest
from app.database import init_db, SessionLocal, RASTER_DIR
from app.models.coverage_site import CoverageSite
from app.routers import nodes as nodes_router
from app.routers import sites as sites_router
from app.routers import projects as projects_router
from app.routers import debug as debug_router
from app.metrics import (
    inc,
    measure,
    result_cache_hits_total,
    setup_instrumentator,
    simulation_duration_seconds,
)
import logging
import io
import time
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery feature flag — when True, tasks are dispatched to Celery workers
USE_CELERY = os.environ.get("USE_CELERY", "false").lower() == "true"

# Initialize Redis client for binary data
redis_client = get_redis_client()

# Initialize FastAPI app
app = FastAPI()

# Prometheus instrumentation (no-op if dependency unavailable)
setup_instrumentator(app)

# Rate limiter (per-IP, using remote address)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware to allow requests from your frontend
allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,https://site.meshtastic.org"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Initialize database tables
init_db()

# Register API routers (must be before static file mount)
app.include_router(nodes_router.router)
app.include_router(sites_router.router)
app.include_router(projects_router.router)
app.include_router(debug_router.router)

def run_splat(task_id: str, request: CoveragePredictionRequest):
    """
    Execute the SPLAT! coverage prediction and store the resulting GeoTIFF data in Redis.

    Args:
        task_id (str): UUID identifier for the task.
        request (CoveragePredictionRequest): The parameters for the SPLAT! prediction.

    Workflow:
        - Runs the SPLAT! coverage prediction.
        - Stores the resulting GeoTIFF data and the task status ("completed") in Redis.
        - On failure, stores the task status as "failed" and logs the error in Redis.

    Raises:
        Exception: If SPLAT! fails during execution.
    """
    sim_status = "failed"
    sim_start = time.perf_counter()
    try:
        logger.info(f"Starting coverage prediction for task {task_id}.")
        engine = get_engine(request.engine)
        geotiff_data = engine.coverage_prediction(request, task_id=task_id)
        sim_status = "success"

        # Log before storing in Redis
        logger.info(f"Storing result in Redis for task {task_id}")
        redis_client.setex(task_id, 3600, geotiff_data)
        redis_client.setex(f"{task_id}:status", 3600, "completed")
        logger.info(f"Task {task_id} marked as completed.")

        # Persist GeoTIFF to disk + database for long-term storage
        try:
            os.makedirs(RASTER_DIR, exist_ok=True)
            raster_path = os.path.join(RASTER_DIR, f"{task_id}.tif")
            with open(raster_path, "wb") as f:
                f.write(geotiff_data)
            db = SessionLocal()
            try:
                site = CoverageSite(
                    task_id=task_id,
                    params=json.dumps(request.model_dump()),
                    raster_path=raster_path,
                )
                db.add(site)
                db.commit()
            finally:
                db.close()
            logger.info(f"Task {task_id} persisted to disk.")
        except Exception as persist_err:
            logger.warning(f"Failed to persist task {task_id} to disk: {persist_err}")
    except Exception as e:
        logger.error(f"Error in SPLAT! task {task_id}: {e}")
        redis_client.setex(f"{task_id}:status", 3600, "failed")
        redis_client.setex(f"{task_id}:error", 3600, str(e))
        raise
    finally:
        if simulation_duration_seconds is not None:
            try:
                simulation_duration_seconds.labels(
                    status=sim_status, queue="inline"
                ).observe(time.perf_counter() - sim_start)
            except Exception:
                pass

def _dispatch_prediction(payload: CoveragePredictionRequest, background_tasks: BackgroundTasks | None = None) -> dict:
    """
    Dispatch a single coverage prediction task.

    Returns dict with task_id and cached flag.
    Reused by both /predict and /predict/batch endpoints.
    """
    rf_hash = payload.rf_param_hash()
    cached_task_id = redis_client.get(f"rfcache:{rf_hash}")
    if cached_task_id:
        cached_task_id = cached_task_id.decode("utf-8")
        cached_status = redis_client.get(f"{cached_task_id}:status")
        if cached_status and cached_status.decode("utf-8") in ("completed", "processing"):
            logger.info(f"RF cache hit for hash {rf_hash}, returning task {cached_task_id}")
            inc(result_cache_hits_total, strategy="rf_hash")
            return {"task_id": cached_task_id, "cached": True}

    # Bbox-aware fuzzy lookup: identical RF params within RF_BBOX_TOLERANCE_DEG of
    # an existing simulation reuse it. Disabled by setting tolerance to 0.
    bbox_tolerance = float(os.environ.get("RF_BBOX_TOLERANCE_DEG", "0.0005"))
    if bbox_tolerance > 0:
        for nbr_hash in payload.rf_neighborhood_hashes(bbox_tolerance):
            if nbr_hash == rf_hash:
                continue
            nbr_task_id = redis_client.get(f"rfbbox:{nbr_hash}")
            if not nbr_task_id:
                continue
            nbr_task_id = nbr_task_id.decode("utf-8")
            nbr_status = redis_client.get(f"{nbr_task_id}:status")
            if nbr_status and nbr_status.decode("utf-8") in ("completed", "processing"):
                logger.info(
                    f"Bbox cache hit (~{bbox_tolerance:g}°) for {rf_hash} -> task {nbr_task_id}"
                )
                inc(result_cache_hits_total, strategy="bbox")
                return {"task_id": nbr_task_id, "cached": True}

    task_id = str(uuid4())
    redis_client.setex(f"{task_id}:status", 3600, "processing")
    redis_client.setex(f"rfcache:{rf_hash}", 3600, task_id)
    if bbox_tolerance > 0:
        # Index by the center neighborhood hash for future fuzzy lookups
        center_hash = payload.rf_neighborhood_hashes(bbox_tolerance)[0]
        redis_client.setex(f"rfbbox:{center_hash}", 3600, task_id)
    if USE_CELERY:
        from app.tasks import run_splat_task
        heavy_threshold = int(os.environ.get("HEAVY_RADIUS_THRESHOLD_KM", "200")) * 1000
        queue = "heavy" if payload.radius > heavy_threshold else "default"
        run_splat_task.apply_async(args=[task_id, payload.model_dump()], queue=queue)
    elif background_tasks:
        background_tasks.add_task(run_splat, task_id, payload)
    return {"task_id": task_id, "cached": False}


@app.post("/predict")
@limiter.limit("5/minute")
async def predict(request: Request, payload: CoveragePredictionRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """
    Predict signal coverage using SPLAT!.
    Accepts a CoveragePredictionRequest and processes it in the background.

    Returns a cached result if the same RF parameters have been computed before.
    Display-only parameters (colormap, min_dbm, max_dbm) are excluded from the cache key.
    """
    result = _dispatch_prediction(payload, background_tasks)
    return JSONResponse(result)


@app.post("/predict/batch")
@limiter.limit("3/minute")
async def predict_batch(request: Request, payloads: List[CoveragePredictionRequest], background_tasks: BackgroundTasks) -> JSONResponse:
    """
    Submit multiple coverage predictions at once.
    All tasks are dispatched simultaneously, allowing the autoscaler to see
    the full queue depth and scale workers accordingly.

    Max 10 predictions per batch.
    """
    if len(payloads) > 10:
        return JSONResponse({"error": "Max 10 predictions per batch"}, status_code=400)
    if len(payloads) == 0:
        return JSONResponse({"error": "At least 1 prediction required"}, status_code=400)

    tasks = [_dispatch_prediction(p, background_tasks) for p in payloads]
    return JSONResponse({"tasks": tasks})

@app.get("/status/{task_id}")
async def get_status(task_id: UUID):
    """
    Retrieve the status of a given SPLAT! task.

    - Checks Redis for the task status.
    - Returns "processing", "completed", or "failed" based on the status.
    - Returns a 404 error if the task ID is not found.

    Args:
        task_id (UUID): The unique identifier for the task.

    Returns:
        JSONResponse: The task status or an error message if the task is not found.
    """
    tid = str(task_id)
    status = redis_client.get(f"{tid}:status")
    if not status:
        # Redis TTL may have expired — check disk before returning 404
        raster_path = os.path.join(RASTER_DIR, f"{tid}.tif")
        if os.path.exists(raster_path):
            logger.info(f"Task {tid} not in Redis but found on disk — returning completed.")
            return JSONResponse({"task_id": tid, "status": "completed"})
        logger.warning(f"Task {tid} not found in Redis or on disk.")
        return JSONResponse({"error": "Task not found"}, status_code=404)

    return JSONResponse({"task_id": tid, "status": status.decode("utf-8")})

@app.get("/events/{task_id}")
async def task_events(task_id: UUID):
    """
    Server-Sent Events stream for real-time task status updates.
    Streams status every 500ms until the task completes or fails.
    """
    tid = str(task_id)

    async def event_generator():
        heartbeat_counter = 0
        while True:
            status = redis_client.get(f"{tid}:status")
            if not status:
                raster_path = os.path.join(RASTER_DIR, f"{tid}.tif")
                if os.path.exists(raster_path):
                    yield f"data: {json.dumps({'task_id': tid, 'status': 'completed'})}\n\n"
                else:
                    yield f"data: {json.dumps({'task_id': tid, 'status': 'not_found'})}\n\n"
                return
            status_str = status.decode("utf-8")
            event_data = {"task_id": tid, "status": status_str}

            # Include progress data if available
            if status_str == "processing":
                progress_raw = redis_client.get(f"{tid}:progress")
                if progress_raw:
                    try:
                        progress = json.loads(progress_raw.decode("utf-8"))
                        event_data.update({
                            "stage": progress.get("stage", ""),
                            "progress": progress.get("progress", 0),
                            "detail": progress.get("detail", ""),
                        })
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        pass

            yield f"data: {json.dumps(event_data)}\n\n"
            if status_str in ("completed", "failed"):
                return

            # Heartbeat every ~15s to keep connection alive
            heartbeat_counter += 1
            if heartbeat_counter % 30 == 0:
                yield ": heartbeat\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/events/multi")
async def multi_task_events(task_ids: str):
    """
    SSE stream that monitors multiple tasks simultaneously.
    Emits an event for each task that reaches a terminal state.
    Closes when all tasks are completed/failed.

    Query param: task_ids — comma-separated list of task UUIDs (max 10).
    """
    ids = [t.strip() for t in task_ids.split(",") if t.strip()]
    if len(ids) > 10:
        return JSONResponse({"error": "Max 10 task IDs"}, status_code=400)
    if not ids:
        return JSONResponse({"error": "No task IDs provided"}, status_code=400)

    async def event_generator():
        pending = set(ids)
        heartbeat_counter = 0

        while pending:
            for tid in list(pending):
                status = redis_client.get(f"{tid}:status")
                if not status:
                    raster_path = os.path.join(RASTER_DIR, f"{tid}.tif")
                    resolved_status = "completed" if os.path.exists(raster_path) else "not_found"
                    event_data = {"task_id": tid, "status": resolved_status}
                    yield f"data: {json.dumps(event_data)}\n\n"
                    pending.discard(tid)
                    continue

                status_str = status.decode("utf-8")
                event_data = {"task_id": tid, "status": status_str}

                # Include progress data if available
                if status_str == "processing":
                    progress_raw = redis_client.get(f"{tid}:progress")
                    if progress_raw:
                        try:
                            progress = json.loads(progress_raw.decode("utf-8"))
                            event_data.update({
                                "stage": progress.get("stage", ""),
                                "progress": progress.get("progress", 0),
                                "detail": progress.get("detail", ""),
                            })
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass

                if status_str in ("completed", "failed"):
                    yield f"data: {json.dumps(event_data)}\n\n"
                    pending.discard(tid)

            if not pending:
                break

            # Emit progress updates for still-processing tasks
            for tid in list(pending):
                status = redis_client.get(f"{tid}:status")
                if status:
                    status_str = status.decode("utf-8")
                    event_data = {"task_id": tid, "status": status_str}
                    progress_raw = redis_client.get(f"{tid}:progress")
                    if progress_raw:
                        try:
                            progress = json.loads(progress_raw.decode("utf-8"))
                            event_data.update({
                                "stage": progress.get("stage", ""),
                                "progress": progress.get("progress", 0),
                                "detail": progress.get("detail", ""),
                            })
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass
                    yield f"data: {json.dumps(event_data)}\n\n"

            # Heartbeat every ~15s to keep connection alive (30 iterations * 0.5s)
            heartbeat_counter += 1
            if heartbeat_counter % 30 == 0:
                yield ": heartbeat\n\n"

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/result/{task_id}")
async def get_result(task_id: UUID):
    """
    Retrieve SPLAT! task status or GeoTIFF result.

    - Checks the task status in Redis.
    - If "completed," retrieves the GeoTIFF data and serves it as a downloadable file.
    - If "failed," returns the error message stored in Redis.
    - If "processing", indicate the same in the response.

    Args:
        task_id (UUID): The unique identifier for the task.

    Returns:
        JSONResponse: Task status if the task is still "processing" or "failed."
        StreamingResponse: A downloadable GeoTIFF file if the task is "completed."
    """
    tid = str(task_id)
    status = redis_client.get(f"{tid}:status")
    if not status:
        # Fall back to disk storage if Redis TTL expired
        raster_path = os.path.join(RASTER_DIR, f"{tid}.tif")
        if os.path.exists(raster_path):
            from fastapi.responses import FileResponse
            logger.info(f"Task {tid} served from disk (Redis expired).")
            return FileResponse(
                raster_path,
                media_type="image/tiff",
                headers={"Content-Disposition": f"attachment; filename={tid}.tif"},
            )
        logger.warning(f"Task {tid} not found in Redis or on disk.")
        return JSONResponse({"error": "Task not found"}, status_code=404)

    status = status.decode("utf-8")
    if status == "completed":
        geotiff_data = redis_client.get(tid)
        if not geotiff_data:
            # Redis data expired but status still present — try disk
            raster_path = os.path.join(RASTER_DIR, f"{tid}.tif")
            if os.path.exists(raster_path):
                from fastapi.responses import FileResponse
                return FileResponse(
                    raster_path,
                    media_type="image/tiff",
                    headers={"Content-Disposition": f"attachment; filename={tid}.tif"},
                )
            logger.error(f"No data found for completed task {tid}.")
            return JSONResponse({"error": "No result found"}, status_code=500)

        geotiff_file = io.BytesIO(geotiff_data)
        return StreamingResponse(
            geotiff_file,
            media_type="image/tiff",
            headers={"Content-Disposition": f"attachment; filename={tid}.tif"}
        )
    elif status == "failed":
        error = redis_client.get(f"{tid}:error")
        return JSONResponse({"status": "failed", "error": error.decode("utf-8")})

    logger.info(f"Task {tid} is still processing.")
    return JSONResponse({"status": "processing"})

app.mount("/", StaticFiles(directory="app/ui", html=True), name="ui")
