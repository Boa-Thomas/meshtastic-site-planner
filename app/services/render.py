"""
High-resolution colorized render of cached SPLAT GeoTIFFs.

Pipeline:
  1. Load grayscale GeoTIFF from Redis or disk (same fallback used by /result).
  2. Optionally reproject EPSG:4326 -> EPSG:3857 (Web Mercator) via rasterio.warp.
  3. Optionally upscale to a target pixel width via PIL Lanczos / Bilinear / Nearest.
  4. Map pixel value 0..247 -> dBm in DCF range [-130, -30] (SPLAT contract),
     then renormalize to the user-chosen [min_dbm, max_dbm] range.
  5. Apply matplotlib colormap and global opacity. NoData (255) -> alpha 0.
  6. Encode as RGBA PNG.

Cached PNGs are keyed by hash of (task_id, colormap, min_dbm, max_dbm, opacity,
width, srs, resample, bbox) and stored in Redis with 1h TTL.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import rasterio
from PIL import Image
from rasterio.io import MemoryFile
from rasterio.warp import Resampling, calculate_default_transform, reproject

from app.database import RASTER_DIR
from app.metrics import (
    inc,
    measure,
    render_cache_events_total,
    render_duration_seconds,
    render_output_pixels,
    render_requests_total,
)
from app.redis_config import get_redis_client

logger = logging.getLogger(__name__)

# Canonical colormaps supported by the frontend (src/utils/colormaps.ts:124-132).
# Render requests with any other name are rejected.
ALLOWED_COLORMAPS = frozenset({
    "plasma", "viridis", "turbo", "jet", "cool", "rainbow", "CMRmap",
})

ALLOWED_RESAMPLES = frozenset({"nearest", "bilinear", "lanczos"})
ALLOWED_SRS = frozenset({"epsg4326", "epsg3857"})
ALLOWED_FORMATS = frozenset({"png"})  # JPEG/COG can be added later.

# UUID v4 by default; permissive enough to accept any 8-4-4-4-12 hex pattern.
# Used as both a Redis key and a filename component, so we MUST reject
# anything that could enable path traversal or unexpected key collisions.
TASK_ID_PATTERN = re.compile(r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$")

# Web Mercator's projected extent in metres (used to sanity-check bbox in 3857).
WEB_MERCATOR_EXTENT = 20037508.342789244

# SPLAT DCF contract: grayscale 0..247 maps linearly to dBm in [-130, -30].
# See app/services/splat.py:_create_splat_dcf.
DCF_MIN_DBM = -130.0
DCF_MAX_DBM = -30.0
DCF_MAX_GRAY = 247.0
NODATA = 255

DEFAULT_OPACITY = 0.85
DEFAULT_RESAMPLE = "lanczos"
DEFAULT_SRS = "epsg3857"

MAX_RENDER_PIXELS = int(os.environ.get("MAX_RENDER_PIXELS", "200000000"))  # 200 MP
MAX_CACHE_PNG_BYTES = int(os.environ.get("MAX_CACHE_PNG_BYTES", str(50 * 1024 * 1024)))
CACHE_TTL_SECONDS = int(os.environ.get("RENDER_CACHE_TTL", "3600"))


@dataclass(frozen=True)
class RenderParams:
    """Validated parameters for a single render request."""
    task_id: str
    colormap: str
    min_dbm: float
    max_dbm: float
    opacity: float
    width: Optional[int]
    srs: str
    resample: str
    bbox: Optional[Tuple[float, float, float, float]]  # west, south, east, north (in srs units)

    def cache_key(self) -> str:
        payload = json.dumps({
            "task_id": self.task_id,
            "colormap": self.colormap,
            "min_dbm": round(self.min_dbm, 3),
            "max_dbm": round(self.max_dbm, 3),
            "opacity": round(self.opacity, 3),
            "width": self.width,
            "srs": self.srs,
            "resample": self.resample,
            "bbox": [round(c, 6) for c in self.bbox] if self.bbox else None,
        }, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"render:{self.task_id}:{digest}"


@dataclass(frozen=True)
class RenderMeta:
    """Metadata describing the rendered image."""
    width: int
    height: int
    srs: str
    bounds: Tuple[float, float, float, float]  # west, south, east, north in srs
    bounds_4326: Tuple[float, float, float, float]
    colormap: str
    min_dbm: float
    max_dbm: float

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "srs": self.srs,
            "bounds": list(self.bounds),
            "bounds_4326": list(self.bounds_4326),
            "colormap": self.colormap,
            "min_dbm": self.min_dbm,
            "max_dbm": self.max_dbm,
        }


# --------------------------------------------------------------------------- #
# Source loading                                                              #
# --------------------------------------------------------------------------- #

def _ensure_pixel_budget(width: int, height: int, context: str = "output") -> None:
    """Raise ValueError if a (width, height) pair exceeds MAX_RENDER_PIXELS."""
    if width <= 0 or height <= 0:
        raise ValueError(f"{context}: invalid dimensions {width}x{height}")
    total = width * height
    if total > MAX_RENDER_PIXELS:
        raise ValueError(
            f"{context}: {width}x{height}={total:,} pixels exceeds "
            f"MAX_RENDER_PIXELS={MAX_RENDER_PIXELS:,}"
        )


def _load_geotiff_bytes(task_id: str) -> bytes:
    """Load the cached GeoTIFF for a task from Redis first, then disk."""
    redis_client = get_redis_client()
    data = redis_client.get(task_id)
    if data:
        logger.debug("Render: loaded GeoTIFF for %s from Redis (%d bytes)", task_id, len(data))
        return data

    raster_path = os.path.join(RASTER_DIR, f"{task_id}.tif")
    if os.path.exists(raster_path):
        with open(raster_path, "rb") as f:
            data = f.read()
        logger.debug("Render: loaded GeoTIFF for %s from disk (%d bytes)", task_id, len(data))
        return data

    raise FileNotFoundError(f"No cached raster found for task_id={task_id}")


# --------------------------------------------------------------------------- #
# Reprojection                                                                #
# --------------------------------------------------------------------------- #

def _reproject_to_srs(
    src_dataset,
    target_srs: str,
    resample: str,
    bbox: Optional[Tuple[float, float, float, float]],
) -> Tuple[np.ndarray, Tuple[float, float, float, float]]:
    """
    Reproject src_dataset (single band, uint8, nodata=255) to target_srs.

    Returns (array2d, bounds_in_target_srs).
    """
    if target_srs == "epsg4326":
        if bbox is not None:
            # Crop window to bbox (west, south, east, north) in EPSG:4326
            west, south, east, north = bbox
            window = rasterio.windows.from_bounds(
                west, south, east, north, transform=src_dataset.transform
            )
            data = src_dataset.read(1, window=window, boundless=True, fill_value=NODATA)
            bounds = (west, south, east, north)
        else:
            data = src_dataset.read(1)
            b = src_dataset.bounds
            bounds = (b.left, b.bottom, b.right, b.top)
        return data, bounds

    # EPSG:3857 path
    dst_crs = "EPSG:3857"
    resampling = getattr(Resampling, resample)

    if bbox is not None:
        # bbox already in 3857 (web mercator metres)
        west, south, east, north = bbox
        # Choose a pixel size matching the source raster's native resolution at
        # this latitude. Source is in degrees -> convert pixelWidth (degrees) to
        # metres at the central latitude (rough but sufficient for resampling).
        from rasterio.warp import transform_bounds
        src_w, _src_s, src_e, _src_n = transform_bounds(
            src_dataset.crs, dst_crs, *src_dataset.bounds, densify_pts=21,
        )
        avg_px_m = abs(src_e - src_w) / src_dataset.width if src_dataset.width else 30.0
        dst_width = max(1, int(round((east - west) / avg_px_m)))
        dst_height = max(1, int(round((north - south) / avg_px_m)))
        dst_transform = rasterio.transform.from_bounds(
            west, south, east, north, dst_width, dst_height,
        )
    else:
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src_dataset.crs, dst_crs,
            src_dataset.width, src_dataset.height,
            *src_dataset.bounds,
        )
        b = rasterio.transform.array_bounds(dst_height, dst_width, dst_transform)
        west, south, east, north = b

    # Guard against OOM: validate reprojected dimensions before allocating.
    # Callers (single + mosaic) re-check the final array size after resize, but
    # an unbounded user-supplied bbox could blow up here long before that.
    _ensure_pixel_budget(dst_width, dst_height, context="reproject")

    out = np.full((dst_height, dst_width), NODATA, dtype=np.uint8)
    reproject(
        source=rasterio.band(src_dataset, 1),
        destination=out,
        src_transform=src_dataset.transform,
        src_crs=src_dataset.crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        src_nodata=NODATA,
        dst_nodata=NODATA,
        resampling=resampling,
    )
    return out, (west, south, east, north)


# --------------------------------------------------------------------------- #
# Resize                                                                      #
# --------------------------------------------------------------------------- #

def _resize_with_mask(
    arr: np.ndarray,
    target_width: int,
    resample: str,
) -> np.ndarray:
    """
    Resize a uint8 raster preserving nodata mask precisely.

    The mask is resized with NEAREST then thresholded; signal data is resized
    with the requested filter on a copy where nodata has been replaced by 0.
    """
    h, w = arr.shape
    if target_width == w:
        return arr
    if target_width <= 0:
        raise ValueError("target_width must be positive")

    aspect = h / w
    target_height = max(1, int(round(target_width * aspect)))

    filter_map = {
        "nearest": Image.NEAREST,
        "bilinear": Image.BILINEAR,
        "lanczos": Image.LANCZOS,
    }
    pil_filter = filter_map[resample]

    nodata_mask = arr == NODATA
    signal = arr.copy()
    signal[nodata_mask] = 0

    signal_img = Image.fromarray(signal, mode="L").resize(
        (target_width, target_height), pil_filter,
    )
    mask_img = Image.fromarray(nodata_mask.astype(np.uint8) * 255, mode="L").resize(
        (target_width, target_height), Image.NEAREST,
    )

    signal_resized = np.array(signal_img)
    mask_resized = np.array(mask_img) > 127
    signal_resized[mask_resized] = NODATA
    return signal_resized


# --------------------------------------------------------------------------- #
# Colorization                                                                #
# --------------------------------------------------------------------------- #

def _colorize(
    data: np.ndarray,
    colormap: str,
    min_dbm: float,
    max_dbm: float,
    opacity: float,
) -> np.ndarray:
    """
    Map pixel values to RGBA using matplotlib colormap.

    Steps:
      - pixel 0..247 -> dBm in DCF range [-130, -30]
      - renormalize to user [min_dbm, max_dbm] via plt.Normalize
      - apply colormap, scale alpha by opacity
      - NoData (255) -> fully transparent
    """
    import matplotlib.pyplot as plt
    cmap = plt.get_cmap(colormap)
    norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm, clip=True)

    nodata_mask = data == NODATA
    dbm = DCF_MIN_DBM + (data.astype(np.float32) / DCF_MAX_GRAY) * (DCF_MAX_DBM - DCF_MIN_DBM)
    rgba = (cmap(norm(dbm)) * 255).astype(np.uint8)  # H x W x 4

    alpha = (rgba[..., 3].astype(np.float32) * opacity).astype(np.uint8)
    rgba[..., 3] = alpha
    rgba[nodata_mask] = (0, 0, 0, 0)
    return rgba


# --------------------------------------------------------------------------- #
# Encoding                                                                    #
# --------------------------------------------------------------------------- #

def _encode_png(rgba: np.ndarray, optimize: bool = True) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG", optimize=optimize)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #

def _validate_task_id(task_id: str) -> None:
    """Reject task_ids that aren't UUID-shaped (path traversal defence)."""
    if not isinstance(task_id, str) or not TASK_ID_PATTERN.match(task_id):
        raise ValueError(f"Invalid task_id format (expected UUID): {task_id!r}")


def _validate_bbox(
    bbox: Tuple[float, float, float, float],
    srs: str,
) -> None:
    """
    Ensure bbox is geometrically sane (west<east, south<north) and lies
    inside the expected coordinate range for the given srs. Rejects NaN/inf.
    """
    if len(bbox) != 4:
        raise ValueError("bbox must be (west, south, east, north)")
    west, south, east, north = bbox
    for label, value in zip(("west", "south", "east", "north"), bbox):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"bbox.{label} must be a finite number, got {value!r}")
    if west >= east:
        raise ValueError(f"bbox: west ({west}) must be less than east ({east})")
    if south >= north:
        raise ValueError(f"bbox: south ({south}) must be less than north ({north})")
    if srs == "epsg4326":
        if not (-180.0 <= west and east <= 180.0):
            raise ValueError(f"bbox: longitude out of range [-180, 180]: {west}..{east}")
        if not (-90.0 <= south and north <= 90.0):
            raise ValueError(f"bbox: latitude out of range [-90, 90]: {south}..{north}")
    elif srs == "epsg3857":
        ext = WEB_MERCATOR_EXTENT
        if not (-ext <= west and east <= ext):
            raise ValueError(f"bbox: x out of Web Mercator extent: {west}..{east}")
        if not (-ext <= south and north <= ext):
            raise ValueError(f"bbox: y out of Web Mercator extent: {south}..{north}")


def validate_params(
    task_id: str,
    colormap: str,
    min_dbm: float,
    max_dbm: float,
    opacity: float,
    width: Optional[int],
    srs: str,
    resample: str,
    bbox: Optional[Tuple[float, float, float, float]],
) -> RenderParams:
    """Validate raw query params, raising ValueError on bad inputs."""
    _validate_task_id(task_id)
    if colormap not in ALLOWED_COLORMAPS:
        raise ValueError(f"Unsupported colormap '{colormap}'. Allowed: {sorted(ALLOWED_COLORMAPS)}")
    if resample not in ALLOWED_RESAMPLES:
        raise ValueError(f"Unsupported resample '{resample}'. Allowed: {sorted(ALLOWED_RESAMPLES)}")
    if srs not in ALLOWED_SRS:
        raise ValueError(f"Unsupported srs '{srs}'. Allowed: {sorted(ALLOWED_SRS)}")
    if not (-200 <= min_dbm < max_dbm <= 50):
        raise ValueError(f"Invalid dBm range: min={min_dbm}, max={max_dbm}")
    if not (0.0 <= opacity <= 1.0):
        raise ValueError(f"Opacity must be in [0,1], got {opacity}")
    if width is not None and (width < 1 or width > 32768):
        raise ValueError(f"Width must be in [1, 32768], got {width}")
    if bbox is not None:
        _validate_bbox(bbox, srs)
    return RenderParams(
        task_id=task_id, colormap=colormap, min_dbm=min_dbm, max_dbm=max_dbm,
        opacity=opacity, width=width, srs=srs, resample=resample, bbox=bbox,
    )


def compute_meta(params: RenderParams) -> RenderMeta:
    """Cheap path: open the source, compute output dimensions/bounds without colorizing."""
    geotiff = _load_geotiff_bytes(params.task_id)
    with MemoryFile(geotiff) as memfile:
        with memfile.open() as src:
            data, bounds = _reproject_to_srs(src, params.srs, params.resample, params.bbox)

    h, w = data.shape
    if params.width is not None and params.width != w:
        aspect = h / w
        h = max(1, int(round(params.width * aspect)))
        w = params.width

    if w * h > MAX_RENDER_PIXELS:
        raise ValueError(
            f"Requested output is {w}x{h}={w*h:,} pixels, exceeds MAX_RENDER_PIXELS={MAX_RENDER_PIXELS:,}"
        )

    # Compute bounds_4326 (always WGS84 corners, useful for the frontend).
    if params.srs == "epsg4326":
        bounds_4326 = bounds
    else:
        from rasterio.warp import transform_bounds
        bounds_4326 = transform_bounds("EPSG:3857", "EPSG:4326", *bounds, densify_pts=21)

    return RenderMeta(
        width=w, height=h, srs=params.srs, bounds=bounds, bounds_4326=bounds_4326,
        colormap=params.colormap, min_dbm=params.min_dbm, max_dbm=params.max_dbm,
    )


def render_colorized(params: RenderParams) -> Tuple[bytes, RenderMeta]:
    """
    Run the full pipeline: load -> reproject -> resize -> colorize -> encode PNG.

    Returns (png_bytes, RenderMeta). Results are cached in Redis when small enough.
    """
    with measure(render_duration_seconds, kind="single"):
        return _render_colorized_inner(params)


def _render_colorized_inner(params: RenderParams) -> Tuple[bytes, RenderMeta]:
    redis_client = get_redis_client()
    cache_key = params.cache_key()
    meta_key = f"{cache_key}:meta"

    cached_png = redis_client.get(cache_key)
    cached_meta = redis_client.get(meta_key)
    if cached_png and cached_meta:
        try:
            meta_dict = json.loads(cached_meta.decode("utf-8"))
            meta = RenderMeta(
                width=meta_dict["width"],
                height=meta_dict["height"],
                srs=meta_dict["srs"],
                bounds=tuple(meta_dict["bounds"]),
                bounds_4326=tuple(meta_dict["bounds_4326"]),
                colormap=meta_dict["colormap"],
                min_dbm=meta_dict["min_dbm"],
                max_dbm=meta_dict["max_dbm"],
            )
            logger.info("Render cache HIT for %s", cache_key)
            inc(render_cache_events_total, kind="single", event="hit")
            inc(render_requests_total, kind="single", outcome="cached")
            return cached_png, meta
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Render cache meta corrupt for %s: %s; re-rendering", cache_key, e)

    inc(render_cache_events_total, kind="single", event="miss")
    logger.info("Render cache MISS for %s; rendering", cache_key)
    geotiff = _load_geotiff_bytes(params.task_id)
    with MemoryFile(geotiff) as memfile:
        with memfile.open() as src:
            data, bounds = _reproject_to_srs(src, params.srs, params.resample, params.bbox)

    if params.width is not None:
        # Validate post-resize size before allocating in _resize_with_mask
        aspect = data.shape[0] / data.shape[1]
        _ensure_pixel_budget(params.width, max(1, int(round(params.width * aspect))), context="single render")
        data = _resize_with_mask(data, params.width, params.resample)

    h, w = data.shape
    try:
        _ensure_pixel_budget(w, h, context="single render")
    except ValueError:
        inc(render_requests_total, kind="single", outcome="too_large")
        raise

    rgba = _colorize(data, params.colormap, params.min_dbm, params.max_dbm, params.opacity)
    png_bytes = _encode_png(rgba)

    if params.srs == "epsg4326":
        bounds_4326 = bounds
    else:
        from rasterio.warp import transform_bounds
        bounds_4326 = transform_bounds("EPSG:3857", "EPSG:4326", *bounds, densify_pts=21)

    meta = RenderMeta(
        width=w, height=h, srs=params.srs, bounds=bounds, bounds_4326=bounds_4326,
        colormap=params.colormap, min_dbm=params.min_dbm, max_dbm=params.max_dbm,
    )

    if len(png_bytes) <= MAX_CACHE_PNG_BYTES:
        redis_client.setex(cache_key, CACHE_TTL_SECONDS, png_bytes)
        redis_client.setex(meta_key, CACHE_TTL_SECONDS, json.dumps(meta.to_dict()))
        inc(render_cache_events_total, kind="single", event="store")
    else:
        inc(render_cache_events_total, kind="single", event="skip_too_large")

    inc(render_requests_total, kind="single", outcome="rendered")
    if render_output_pixels is not None:
        try:
            render_output_pixels.labels(kind="single").observe(w * h)
        except Exception:
            pass

    return png_bytes, meta


@dataclass(frozen=True)
class MosaicParams:
    """Validated parameters for a multi-site mosaic render."""
    task_ids: Tuple[str, ...]
    colormap: str
    min_dbm: float
    max_dbm: float
    opacity: float
    width: Optional[int]
    srs: str
    resample: str
    bbox: Optional[Tuple[float, float, float, float]]

    def cache_key(self) -> str:
        payload = json.dumps({
            "task_ids": sorted(self.task_ids),
            "colormap": self.colormap,
            "min_dbm": round(self.min_dbm, 3),
            "max_dbm": round(self.max_dbm, 3),
            "opacity": round(self.opacity, 3),
            "width": self.width,
            "srs": self.srs,
            "resample": self.resample,
            "bbox": [round(c, 6) for c in self.bbox] if self.bbox else None,
        }, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"mosaic:{digest}"


def validate_mosaic_params(
    task_ids: Tuple[str, ...],
    colormap: str,
    min_dbm: float,
    max_dbm: float,
    opacity: float,
    width: Optional[int],
    srs: str,
    resample: str,
    bbox: Optional[Tuple[float, float, float, float]],
) -> MosaicParams:
    if not task_ids:
        raise ValueError("At least one task_id required")
    if len(task_ids) > 20:
        raise ValueError(f"Too many task_ids ({len(task_ids)}); max 20")
    # Validate each task_id and the shared render params via the single-render
    # validator. Using the first task_id keeps a single source of truth for
    # colormap/opacity/etc rules.
    for tid in task_ids:
        _validate_task_id(tid)
    validate_params(
        task_ids[0], colormap, min_dbm, max_dbm, opacity, width, srs, resample, bbox,
    )
    return MosaicParams(
        task_ids=tuple(task_ids), colormap=colormap, min_dbm=min_dbm, max_dbm=max_dbm,
        opacity=opacity, width=width, srs=srs, resample=resample, bbox=bbox,
    )


def _compute_mosaic_bounds_native(task_ids: Tuple[str, ...]) -> Tuple[float, float, float, float]:
    """Union of all source rasters' WGS84 bounds."""
    west, south, east, north = math.inf, math.inf, -math.inf, -math.inf
    for tid in task_ids:
        geotiff = _load_geotiff_bytes(tid)
        with MemoryFile(geotiff) as memfile:
            with memfile.open() as src:
                b = src.bounds
                west = min(west, b.left)
                south = min(south, b.bottom)
                east = max(east, b.right)
                north = max(north, b.top)
    return west, south, east, north


def render_mosaic(params: MosaicParams) -> Tuple[bytes, RenderMeta]:
    """
    Render multiple coverage rasters into a single colorized PNG.

    Combination rule: per-pixel **max** of grayscale values (the strongest
    signal at each location wins). This matches how a real mesh network
    behaves -- the best receivable signal is what matters.
    """
    with measure(render_duration_seconds, kind="mosaic"):
        return _render_mosaic_inner(params)


def _render_mosaic_inner(params: MosaicParams) -> Tuple[bytes, RenderMeta]:
    redis_client = get_redis_client()
    cache_key = params.cache_key()
    meta_key = f"{cache_key}:meta"

    cached_png = redis_client.get(cache_key)
    cached_meta = redis_client.get(meta_key)
    if cached_png and cached_meta:
        try:
            md = json.loads(cached_meta.decode("utf-8"))
            meta = RenderMeta(
                width=md["width"], height=md["height"], srs=md["srs"],
                bounds=tuple(md["bounds"]), bounds_4326=tuple(md["bounds_4326"]),
                colormap=md["colormap"], min_dbm=md["min_dbm"], max_dbm=md["max_dbm"],
            )
            logger.info("Mosaic cache HIT for %s", cache_key)
            inc(render_cache_events_total, kind="mosaic", event="hit")
            inc(render_requests_total, kind="mosaic", outcome="cached")
            return cached_png, meta
        except (json.JSONDecodeError, KeyError):
            pass

    inc(render_cache_events_total, kind="mosaic", event="miss")
    logger.info("Mosaic cache MISS for %s; rendering %d tasks", cache_key, len(params.task_ids))

    # Determine the output bbox: if user provided one, use it; otherwise union
    # of the source rasters' bounds (in EPSG:4326, then reproject if needed).
    if params.bbox is not None:
        out_bbox = params.bbox
    else:
        west, south, east, north = _compute_mosaic_bounds_native(params.task_ids)
        if params.srs == "epsg3857":
            from rasterio.warp import transform_bounds
            out_bbox = transform_bounds(
                "EPSG:4326", "EPSG:3857", west, south, east, north, densify_pts=21,
            )
        else:
            out_bbox = (west, south, east, north)

    # Reproject each source into the common output frame. We do this by passing
    # the explicit `bbox` to _reproject_to_srs, which produces aligned arrays.
    layers: list[np.ndarray] = []
    target_shape: Optional[Tuple[int, int]] = None
    bounds_used: Optional[Tuple[float, float, float, float]] = None
    for tid in params.task_ids:
        geotiff = _load_geotiff_bytes(tid)
        with MemoryFile(geotiff) as memfile:
            with memfile.open() as src:
                data, bounds = _reproject_to_srs(src, params.srs, params.resample, out_bbox)
        if target_shape is None:
            target_shape = data.shape
            bounds_used = bounds
        elif data.shape != target_shape:
            # Reprojected sizes diverged slightly due to rounding -- resample
            # to the first layer's shape using nearest (preserves nodata).
            data = _resize_with_mask(data, target_shape[1], "nearest")
            if data.shape[0] != target_shape[0]:
                # Final-pass crop/pad to match exactly
                arr = np.full(target_shape, NODATA, dtype=np.uint8)
                rows = min(data.shape[0], target_shape[0])
                cols = min(data.shape[1], target_shape[1])
                arr[:rows, :cols] = data[:rows, :cols]
                data = arr
        layers.append(data)

    assert target_shape is not None and bounds_used is not None

    # Max-combine: strongest pixel value (= strongest signal) wins.
    # Treat 255 (nodata) as "no signal", so we need to compute max over
    # non-nodata values, then fill nodata where nobody had signal.
    combined = np.full(target_shape, NODATA, dtype=np.uint8)
    for layer in layers:
        signal_mask = layer != NODATA
        combined_mask = combined != NODATA
        # Where only one side has data, take it directly
        take_layer = signal_mask & ~combined_mask
        take_combined = ~signal_mask & combined_mask
        take_max = signal_mask & combined_mask
        combined = np.where(take_layer, layer, combined)
        combined = np.where(take_max, np.maximum(layer, combined), combined)
        # take_combined: combined stays as-is
        del take_layer, take_combined, take_max

    if params.width is not None:
        combined = _resize_with_mask(combined, params.width, params.resample)

    h, w = combined.shape
    try:
        _ensure_pixel_budget(w, h, context="mosaic")
    except ValueError:
        inc(render_requests_total, kind="mosaic", outcome="too_large")
        raise

    rgba = _colorize(combined, params.colormap, params.min_dbm, params.max_dbm, params.opacity)
    png_bytes = _encode_png(rgba)

    if params.srs == "epsg4326":
        bounds_4326 = bounds_used
    else:
        from rasterio.warp import transform_bounds
        bounds_4326 = transform_bounds("EPSG:3857", "EPSG:4326", *bounds_used, densify_pts=21)

    meta = RenderMeta(
        width=w, height=h, srs=params.srs, bounds=bounds_used, bounds_4326=bounds_4326,
        colormap=params.colormap, min_dbm=params.min_dbm, max_dbm=params.max_dbm,
    )

    if len(png_bytes) <= MAX_CACHE_PNG_BYTES:
        redis_client.setex(cache_key, CACHE_TTL_SECONDS, png_bytes)
        redis_client.setex(meta_key, CACHE_TTL_SECONDS, json.dumps(meta.to_dict()))
        inc(render_cache_events_total, kind="mosaic", event="store")
    else:
        inc(render_cache_events_total, kind="mosaic", event="skip_too_large")

    inc(render_requests_total, kind="mosaic", outcome="rendered")
    if render_output_pixels is not None:
        try:
            render_output_pixels.labels(kind="mosaic").observe(w * h)
        except Exception:
            pass

    return png_bytes, meta


def render_colorbar(colormap: str, min_dbm: float, max_dbm: float, width: int = 400, height: int = 40) -> bytes:
    """Render a horizontal colorbar PNG with min/max dBm tick labels."""
    if colormap not in ALLOWED_COLORMAPS:
        raise ValueError(f"Unsupported colormap '{colormap}'")
    if width < 50 or width > 2000 or height < 10 or height > 200:
        raise ValueError("colorbar dimensions out of range")

    import matplotlib.pyplot as plt
    cmap = plt.get_cmap(colormap)
    norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)
    ramp = np.linspace(min_dbm, max_dbm, width)
    rgba = (cmap(norm(ramp)) * 255).astype(np.uint8)
    bar = np.tile(rgba[np.newaxis, :, :], (height, 1, 1))
    return _encode_png(bar)
