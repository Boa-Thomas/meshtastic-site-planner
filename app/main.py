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
import redis
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from uuid import uuid4, UUID
from starlette.requests import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.services.splat import Splat
from app.models.CoveragePredictionRequest import CoveragePredictionRequest
import logging
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Redis client for binary data
redis_client = redis.StrictRedis(host="redis", port=6379, decode_responses=False)

# Initialize SPLAT service
splat_service = Splat(splat_path="/app/splat")

# Initialize FastAPI app
app = FastAPI()

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
    try:
        logger.info(f"Starting SPLAT! coverage prediction for task {task_id}.")
        geotiff_data = splat_service.coverage_prediction(request)

        # Log before storing in Redis
        logger.info(f"Storing result in Redis for task {task_id}")
        redis_client.setex(task_id, 3600, geotiff_data)
        redis_client.setex(f"{task_id}:status", 3600, "completed")
        logger.info(f"Task {task_id} marked as completed.")
    except Exception as e:
        logger.error(f"Error in SPLAT! task {task_id}: {e}")
        redis_client.setex(f"{task_id}:status", 3600, "failed")
        redis_client.setex(f"{task_id}:error", 3600, str(e))
        raise

@app.post("/predict")
@limiter.limit("5/minute")
async def predict(request: Request, payload: CoveragePredictionRequest, background_tasks: BackgroundTasks) -> JSONResponse:
    """
    Predict signal coverage using SPLAT!.
    Accepts a CoveragePredictionRequest and processes it in the background.

    Returns a cached result if the same RF parameters have been computed before.
    Display-only parameters (colormap, min_dbm, max_dbm) are excluded from the cache key.

    Args:
        payload (CoveragePredictionRequest): The parameters required for the SPLAT! coverage prediction.
        background_tasks (BackgroundTasks): FastAPI background tasks.

    Returns:
        JSONResponse: A response containing the unique task ID to track the prediction progress.
    """
    # Check RF parameter cache — return existing task if same RF params were already computed
    rf_hash = payload.rf_param_hash()
    cached_task_id = redis_client.get(f"rfcache:{rf_hash}")
    if cached_task_id:
        cached_task_id = cached_task_id.decode("utf-8")
        cached_status = redis_client.get(f"{cached_task_id}:status")
        if cached_status and cached_status.decode("utf-8") in ("completed", "processing"):
            logger.info(f"RF cache hit for hash {rf_hash}, returning task {cached_task_id}")
            return JSONResponse({"task_id": cached_task_id, "cached": True})

    task_id = str(uuid4())
    redis_client.setex(f"{task_id}:status", 3600, "processing")
    redis_client.setex(f"rfcache:{rf_hash}", 3600, task_id)
    background_tasks.add_task(run_splat, task_id, payload)
    return JSONResponse({"task_id": task_id})

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
        logger.warning(f"Task {tid} not found in Redis.")
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
        while True:
            status = redis_client.get(f"{tid}:status")
            if not status:
                yield f"data: {json.dumps({'task_id': tid, 'status': 'not_found'})}\n\n"
                return
            status_str = status.decode("utf-8")
            yield f"data: {json.dumps({'task_id': tid, 'status': status_str})}\n\n"
            if status_str in ("completed", "failed"):
                return
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
        logger.warning(f"Task {tid} not found in Redis.")
        return JSONResponse({"error": "Task not found"}, status_code=404)

    status = status.decode("utf-8")
    if status == "completed":
        geotiff_data = redis_client.get(tid)
        if not geotiff_data:
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
