"""High-resolution colorized render endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from app.services.render import (
    ALLOWED_COLORMAPS,
    DEFAULT_OPACITY,
    DEFAULT_RESAMPLE,
    DEFAULT_SRS,
    compute_meta,
    render_colorbar,
    render_colorized,
    render_mosaic,
    validate_mosaic_params,
    validate_params,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/render", tags=["render"])


def _parse_bbox(bbox_str: Optional[str]):
    if bbox_str is None:
        return None
    try:
        parts = [float(x) for x in bbox_str.split(",")]
    except ValueError:
        raise HTTPException(400, "bbox must be 4 comma-separated floats: west,south,east,north")
    if len(parts) != 4:
        raise HTTPException(400, "bbox must contain exactly 4 values")
    return tuple(parts)


@router.get("/mosaic")
async def get_render_mosaic(
    task_ids: str = Query(..., description="comma-separated task UUIDs (max 20)"),
    colormap: str = Query("plasma"),
    min_dbm: float = Query(-130.0),
    max_dbm: float = Query(-50.0),
    opacity: float = Query(DEFAULT_OPACITY, ge=0.0, le=1.0),
    width: Optional[int] = Query(None, ge=1, le=32768),
    srs: str = Query(DEFAULT_SRS),
    resample: str = Query(DEFAULT_RESAMPLE),
    bbox: Optional[str] = Query(None, description="west,south,east,north in srs units"),
):
    """
    Render multiple tasks into a single colorized PNG using per-pixel max
    combination (strongest signal wins).
    """
    ids = tuple(t.strip() for t in task_ids.split(",") if t.strip())
    if not ids:
        raise HTTPException(400, "No task_ids provided")
    bbox_tuple = _parse_bbox(bbox)
    try:
        params = validate_mosaic_params(
            task_ids=ids, colormap=colormap, min_dbm=min_dbm, max_dbm=max_dbm,
            opacity=opacity, width=width, srs=srs, resample=resample, bbox=bbox_tuple,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        png_bytes, meta = await run_in_threadpool(render_mosaic, params)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(413, str(e))
    except Exception as e:
        logger.exception("render_mosaic failed for %s", ids)
        raise HTTPException(500, f"Mosaic render failed: {e}")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-Render-Meta": json.dumps(meta.to_dict()),
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/colorbar")
def get_colorbar(
    colormap: str = Query("plasma"),
    min_dbm: float = Query(-130.0),
    max_dbm: float = Query(-50.0),
    width: int = Query(400, ge=50, le=2000),
    height: int = Query(40, ge=10, le=200),
):
    """Return a horizontal colorbar PNG sized to the requested width/height."""
    if colormap not in ALLOWED_COLORMAPS:
        raise HTTPException(400, f"Unsupported colormap '{colormap}'")
    if min_dbm >= max_dbm:
        raise HTTPException(400, "min_dbm must be less than max_dbm")
    try:
        png = render_colorbar(colormap, min_dbm, max_dbm, width, height)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/{task_id}/meta")
async def get_render_meta(
    task_id: str,
    colormap: str = Query("plasma"),
    min_dbm: float = Query(-130.0),
    max_dbm: float = Query(-50.0),
    opacity: float = Query(DEFAULT_OPACITY, ge=0.0, le=1.0),
    width: Optional[int] = Query(None, ge=1, le=32768),
    srs: str = Query(DEFAULT_SRS),
    resample: str = Query(DEFAULT_RESAMPLE),
    bbox: Optional[str] = Query(None, description="west,south,east,north in srs units"),
):
    """Cheap preflight: returns output dimensions and bounds without colorizing."""
    bbox_tuple = _parse_bbox(bbox)
    try:
        params = validate_params(
            task_id=task_id, colormap=colormap, min_dbm=min_dbm, max_dbm=max_dbm,
            opacity=opacity, width=width, srs=srs, resample=resample, bbox=bbox_tuple,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        meta = await run_in_threadpool(compute_meta, params)
    except FileNotFoundError:
        raise HTTPException(404, "Task result not found")
    except ValueError as e:
        raise HTTPException(413, str(e))
    except Exception as e:
        logger.exception("compute_meta failed for %s", task_id)
        raise HTTPException(500, f"Failed to compute render metadata: {e}")

    return JSONResponse(meta.to_dict())


@router.get("/{task_id}")
async def get_render(
    task_id: str,
    colormap: str = Query("plasma"),
    min_dbm: float = Query(-130.0),
    max_dbm: float = Query(-50.0),
    opacity: float = Query(DEFAULT_OPACITY, ge=0.0, le=1.0),
    width: Optional[int] = Query(None, ge=1, le=32768),
    srs: str = Query(DEFAULT_SRS),
    resample: str = Query(DEFAULT_RESAMPLE),
    bbox: Optional[str] = Query(None, description="west,south,east,north in srs units"),
):
    """Render a colorized PNG of a cached coverage task."""
    bbox_tuple = _parse_bbox(bbox)
    try:
        params = validate_params(
            task_id=task_id, colormap=colormap, min_dbm=min_dbm, max_dbm=max_dbm,
            opacity=opacity, width=width, srs=srs, resample=resample, bbox=bbox_tuple,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        png_bytes, meta = await run_in_threadpool(render_colorized, params)
    except FileNotFoundError:
        raise HTTPException(404, "Task result not found")
    except ValueError as e:
        raise HTTPException(413, str(e))
    except Exception as e:
        logger.exception("render_colorized failed for %s", task_id)
        raise HTTPException(500, f"Render failed: {e}")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "X-Render-Meta": json.dumps(meta.to_dict()),
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": f"inline; filename={task_id}.png",
        },
    )
