"""Factory for propagation engine instances.

Engines are cached per (engine_name, dem_source, clutter_source, factor) tuple
so a single process can serve requests with different DEM / clutter settings
without rebuilding boto3 / Redis clients on every call. The cache key is the
*resolved* configuration (after env-var fallback), not the raw request, so
identical requests share the same engine instance.
"""

import logging
import os
from typing import Optional

from app.services.clutter import ClutterSource, CLUTTER_SOURCES, clutter_source_config
from app.services.engine import PropagationEngine

logger = logging.getLogger(__name__)

# Singleton cache keyed by (engine_name, dem_source, clutter_source, factor).
_engines: dict[tuple, PropagationEngine] = {}

DEFAULT_ENGINE = os.environ.get("PROPAGATION_ENGINE", "splat")
DEFAULT_DEM_SOURCE = os.environ.get("DEM_SOURCE", "srtm")
DEFAULT_CLUTTER_SOURCE = os.environ.get("CLUTTER_SOURCE", "none")


def _resolve_clutter_source(
    name: Optional[str], factor: Optional[float]
) -> Optional[ClutterSource]:
    """Build a ClutterSource for the resolved name + factor, or None.

    Honours the same env vars as `make_clutter_source_from_env` for bucket /
    prefix / filename — only the source name and the penetration factor are
    request-overridable. Operators don't expose buckets to clients.
    """
    src = (name or DEFAULT_CLUTTER_SOURCE or "none").lower().strip()
    if src in ("", "none"):
        return None
    if src not in CLUTTER_SOURCES:
        raise ValueError(
            f"Unknown clutter source '{src}'. Supported: {sorted(CLUTTER_SOURCES.keys())}"
        )
    cfg = clutter_source_config(src)
    resolved_factor = (
        factor if factor is not None
        else float(os.environ.get("CLUTTER_PENETRATION_FACTOR", "0.6"))
    )
    return ClutterSource(
        name=src,
        bucket=cfg["bucket"],
        prefix=cfg["prefix"],
        filename_template=cfg["filename_template"],
        penetration_factor=resolved_factor,
    )


def get_engine(
    name: Optional[str] = None,
    dem_source: Optional[str] = None,
    clutter_source: Optional[str] = None,
    clutter_penetration_factor: Optional[float] = None,
) -> PropagationEngine:
    """
    Get or create a propagation engine for the given configuration.

    Args:
        name: Engine name ("splat" or "signal_server"). Defaults to env.
        dem_source: DEM source override (splat only). Defaults to DEM_SOURCE env.
        clutter_source: Clutter source override (splat only). 'none' disables.
        clutter_penetration_factor: Override for the penetration factor.

    Returns:
        A PropagationEngine instance, cached for this configuration.

    Raises:
        ValueError: If the engine name or DEM source is unknown.
        RuntimeError: If the engine is not available on this system.
    """
    engine_name = (name or DEFAULT_ENGINE).lower().strip()
    resolved_dem = (dem_source or DEFAULT_DEM_SOURCE).lower().strip()
    resolved_clutter_name = (clutter_source or DEFAULT_CLUTTER_SOURCE or "none").lower().strip()
    if resolved_clutter_name == "":
        resolved_clutter_name = "none"
    resolved_factor = (
        clutter_penetration_factor if clutter_penetration_factor is not None
        else float(os.environ.get("CLUTTER_PENETRATION_FACTOR", "0.6"))
    )

    cache_key = (engine_name, resolved_dem, resolved_clutter_name, resolved_factor)
    if cache_key in _engines:
        return _engines[cache_key]

    if engine_name == "splat":
        from app.services.splat import Splat
        splat_path = os.environ.get("SPLAT_PATH", "/app/splat")
        cache_dir = os.environ.get("SPLAT_TILE_CACHE", ".splat_tiles")
        cache_size_gb = float(os.environ.get("SPLAT_TILE_CACHE_SIZE_GB", "10"))
        clutter_obj = _resolve_clutter_source(resolved_clutter_name, resolved_factor)
        engine = Splat(
            splat_path=splat_path,
            cache_dir=cache_dir,
            cache_size_gb=cache_size_gb,
            dem_source=resolved_dem,
            clutter_source=clutter_obj,
        )
    elif engine_name == "signal_server":
        from app.services.signal_server import SignalServerEngine
        binary = os.environ.get("SIGNAL_SERVER_PATH", "/usr/local/bin/signalserverHD")
        sdf_path = os.environ.get("SIGNAL_SERVER_SDF_PATH", "")
        model = os.environ.get("SIGNAL_SERVER_MODEL", "itm")
        engine = SignalServerEngine(binary_path=binary, sdf_path=sdf_path, default_model=model)
    else:
        raise ValueError(
            f"Unknown propagation engine: '{engine_name}'. "
            f"Available: 'splat', 'signal_server'"
        )

    if not engine.is_available():
        raise RuntimeError(
            f"Propagation engine '{engine_name}' is not available. "
            f"Check that binaries are installed and accessible."
        )

    _engines[cache_key] = engine
    logger.info(
        f"Created propagation engine: {engine_name} "
        f"(dem={resolved_dem}, clutter={resolved_clutter_name}, factor={resolved_factor})"
    )
    return engine


def get_engine_for_request(request) -> PropagationEngine:
    """Convenience wrapper: pull DEM / clutter overrides off a request payload."""
    return get_engine(
        name=getattr(request, "engine", None),
        dem_source=getattr(request, "dem_source", None),
        clutter_source=getattr(request, "clutter_source", None),
        clutter_penetration_factor=getattr(request, "clutter_penetration_factor", None),
    )
