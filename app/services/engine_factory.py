"""Factory for propagation engine instances."""

import logging
import os
from typing import Optional

from app.services.engine import PropagationEngine

logger = logging.getLogger(__name__)

# Singleton cache: engine name -> instance
_engines: dict[str, PropagationEngine] = {}

DEFAULT_ENGINE = os.environ.get("PROPAGATION_ENGINE", "splat")


def get_engine(name: Optional[str] = None) -> PropagationEngine:
    """
    Get or create a propagation engine by name.

    Args:
        name: Engine name ("splat" or "signal_server"). Defaults to
              the PROPAGATION_ENGINE env var, or "splat".

    Returns:
        A PropagationEngine instance.

    Raises:
        ValueError: If the engine name is unknown.
        RuntimeError: If the engine is not available on this system.
    """
    engine_name = (name or DEFAULT_ENGINE).lower().strip()

    if engine_name in _engines:
        return _engines[engine_name]

    if engine_name == "splat":
        from app.services.splat import Splat
        splat_path = os.environ.get("SPLAT_PATH", "/app/splat")
        cache_dir = os.environ.get("SPLAT_TILE_CACHE", ".splat_tiles")
        cache_size_gb = float(os.environ.get("SPLAT_TILE_CACHE_SIZE_GB", "10"))
        engine = Splat(splat_path=splat_path, cache_dir=cache_dir,
                       cache_size_gb=cache_size_gb)
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

    _engines[engine_name] = engine
    logger.info(f"Created propagation engine: {engine_name}")
    return engine
