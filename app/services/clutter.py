"""
Spatial clutter (canopy / vegetation height) service.

The SPLAT! ITM model only accepts a single uniform clutter height via ``-gc``.
This module replaces that with per-pixel canopy data: the canopy raster is
added on top of the DTM before the .hgt.gz is handed to ``srtm2sdf``, so the
model sees a synthetic DSM that incorporates real vegetation height.

Operators host the canopy tiles themselves (e.g. a mirror of Lang et al. 2023
or MapBiomas). All knobs are env-driven:

    CLUTTER_SOURCE             one of: none (default), lang2023, mapbiomas, custom
    CLUTTER_BUCKET             S3 bucket holding 1°×1° canopy GeoTIFFs
    CLUTTER_PREFIX             optional prefix inside the bucket
    CLUTTER_FILENAME_TEMPLATE  default: "{ns}{lat:02d}{ew}{lon:03d}.tif"
    CLUTTER_PENETRATION_FACTOR scales canopy height to model RF penetration
                               (0.0 = trees invisible, 1.0 = solid wall).
                               Default 0.6 — calibrate against field data.

The synthetic DSM is built tile-by-tile:
    synthetic_elevation = dtm_elevation + canopy_height * penetration_factor

When ``CLUTTER_SOURCE`` is unset or "none", the Splat engine behaves exactly
like before (and the legacy ``-gc`` knob still applies).
"""

from __future__ import annotations

import io
import logging
import os
from typing import Optional

import boto3
import numpy as np
import rasterio
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from rasterio.enums import Resampling

logger = logging.getLogger(__name__)

# Known canopy datasets and their default bucket/prefix conventions. Operators
# can still override everything via env vars; this just gives sensible defaults
# per source name.
CLUTTER_SOURCES = {
    "lang2023": {
        # ETH Global Canopy Height 10 m, Lang et al. 2023.
        # No public AWS Open Data mirror; defaults assume an operator mirror.
        "bucket": os.environ.get("CLUTTER_BUCKET", ""),
        "prefix": os.environ.get("CLUTTER_PREFIX", ""),
        "filename_template": os.environ.get(
            "CLUTTER_FILENAME_TEMPLATE", "{ns}{lat:02d}{ew}{lon:03d}.tif"
        ),
    },
    "mapbiomas": {
        # MapBiomas Brazil annual vegetation height. Brazil-only.
        "bucket": os.environ.get("CLUTTER_BUCKET", ""),
        "prefix": os.environ.get("CLUTTER_PREFIX", ""),
        "filename_template": os.environ.get(
            "CLUTTER_FILENAME_TEMPLATE", "mapbiomas_{ns}{lat:02d}{ew}{lon:03d}.tif"
        ),
    },
    "custom": {
        # Fully operator-defined. Requires CLUTTER_BUCKET to be set.
        "bucket": os.environ.get("CLUTTER_BUCKET", ""),
        "prefix": os.environ.get("CLUTTER_PREFIX", ""),
        "filename_template": os.environ.get(
            "CLUTTER_FILENAME_TEMPLATE", "{ns}{lat:02d}{ew}{lon:03d}.tif"
        ),
    },
}


class ClutterSource:
    """Loader for per-pixel canopy / vegetation height tiles.

    A tile is returned as a 3601×3601 float32 array of *effective* heights in
    meters (raw canopy height already multiplied by the penetration factor),
    aligned to the same 1°×1° grid the DTM tiles use so the two can be summed
    cell-by-cell.
    """

    def __init__(
        self,
        name: str,
        bucket: str,
        prefix: str,
        filename_template: str,
        penetration_factor: float,
        s3_client=None,
    ):
        if not bucket:
            raise ValueError(
                f"Clutter source '{name}' requires CLUTTER_BUCKET to be set."
            )
        self.name = name
        self.bucket = bucket
        self.prefix = prefix
        self.filename_template = filename_template
        self.penetration_factor = float(penetration_factor)
        if not (0.0 <= self.penetration_factor <= 1.0):
            raise ValueError(
                f"CLUTTER_PENETRATION_FACTOR must be in [0, 1]; got {penetration_factor}"
            )
        self.s3 = s3_client or boto3.client(
            "s3",
            config=Config(
                signature_version=UNSIGNED,
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )

    def s3_key(self, tile_name: str) -> str:
        """SRTM-style filename → canopy GeoTIFF S3 key."""
        ns = tile_name[0]
        lat = int(tile_name[1:3])
        ew = tile_name[3]
        lon = int(tile_name[4:7])
        fname = self.filename_template.format(ns=ns, ew=ew, lat=lat, lon=lon)
        return f"{self.prefix.rstrip('/')}/{fname}" if self.prefix else fname

    def get_effective_height_grid(self, tile_name: str) -> Optional[np.ndarray]:
        """Return a 3601×3601 float32 array of canopy heights in meters.

        Heights are already multiplied by the penetration factor — caller just
        adds them to the DTM. Returns None if the tile is missing (clean signal
        for "no vegetation data here, treat as bare ground").
        """
        key = self.s3_key(tile_name)
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=key)
            cog_bytes = obj["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.info(f"No canopy tile for {tile_name} at {self.bucket}/{key}; treating as bare ground")
                return None
            raise

        with rasterio.MemoryFile(cog_bytes) as memfile:
            with memfile.open() as src:
                data = src.read(
                    1,
                    out_shape=(3601, 3601),
                    resampling=Resampling.bilinear,
                ).astype("float32")
                src_nodata = src.nodata

        if src_nodata is not None:
            data = np.where(data == src_nodata, 0.0, data)
        # Treat negative / NaN / wildly-negative as zero canopy.
        data = np.where(np.isfinite(data) & (data > 0), data, 0.0)
        return data * self.penetration_factor


def make_clutter_source_from_env() -> Optional[ClutterSource]:
    """Build a ClutterSource from environment variables, or None if disabled."""
    src = os.environ.get("CLUTTER_SOURCE", "none").lower().strip()
    if src in ("", "none"):
        return None
    if src not in CLUTTER_SOURCES:
        raise ValueError(
            f"Unknown CLUTTER_SOURCE '{src}'. "
            f"Supported: {sorted(CLUTTER_SOURCES.keys())}"
        )
    cfg = CLUTTER_SOURCES[src]
    penetration = float(os.environ.get("CLUTTER_PENETRATION_FACTOR", "0.6"))
    return ClutterSource(
        name=src,
        bucket=cfg["bucket"],
        prefix=cfg["prefix"],
        filename_template=cfg["filename_template"],
        penetration_factor=penetration,
    )
