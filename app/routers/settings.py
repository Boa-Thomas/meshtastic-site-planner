"""Settings endpoints — surface server-side terrain/clutter config to the UI.

The DEM pipeline is configured exclusively via env vars (so secrets / bucket
credentials never leak through the API). This router exposes a *read-only*
view of that config plus the choices the UI can offer for per-request
overrides. Operators set the defaults; clients pick a source per request.
"""

import os
from fastapi import APIRouter

from app.services.clutter import CLUTTER_SOURCES
from app.services.splat import DEM_SOURCES

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _bool_env(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


@router.get("/terrain")
def get_terrain_settings():
    """
    Return the active terrain pipeline configuration plus the per-request
    overrides the UI can offer.

    Buckets / prefixes / API keys are intentionally NOT included.
    """
    default_dem = os.environ.get("DEM_SOURCE", "srtm").lower().strip()
    default_clutter = (os.environ.get("CLUTTER_SOURCE", "none") or "none").lower().strip()
    default_factor = float(os.environ.get("CLUTTER_PENETRATION_FACTOR", "0.6"))

    # Mark sources as "ready" only when the corresponding bucket is configured
    # — clients can then disable choices that would error out.
    fabdem_ready = bool(os.environ.get("FABDEM_BUCKET"))
    clutter_ready = bool(os.environ.get("CLUTTER_BUCKET"))

    available_dem_sources = []
    for name in sorted(DEM_SOURCES.keys()):
        ready = True
        note = None
        if name == "fabdem" and not fabdem_ready:
            ready = False
            note = "FABDEM_BUCKET not configured on this server"
        available_dem_sources.append({"id": name, "ready": ready, "note": note})

    available_clutter_sources = [{"id": "none", "ready": True, "note": None}]
    for name in sorted(CLUTTER_SOURCES.keys()):
        ready = clutter_ready
        note = None if ready else "CLUTTER_BUCKET not configured on this server"
        available_clutter_sources.append({"id": name, "ready": ready, "note": note})

    return {
        "defaults": {
            "dem_source": default_dem,
            "clutter_source": default_clutter,
            "clutter_penetration_factor": default_factor,
            "fabdem_fallback_source": os.environ.get("FABDEM_FALLBACK_SOURCE", "copernicus"),
        },
        "dem_sources": available_dem_sources,
        "clutter_sources": available_clutter_sources,
        "calibration": {
            # When True, the UI can show a "this default is uncalibrated"
            # warning so operators know the factor is a placeholder.
            "factor_calibrated": _bool_env("CLUTTER_FACTOR_CALIBRATED", False),
            "calibration_notes": os.environ.get("CLUTTER_CALIBRATION_NOTES", ""),
        },
    }
