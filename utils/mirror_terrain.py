"""
Terrain / canopy mirror ingestion CLI.

Bridges the operator gap left by the DEM multi-source pipeline: FABDEM and
canopy datasets (Lang 2023, MapBiomas, ...) cannot be bundled in this repo
because of license restrictions, so the operator must host their own S3
mirror. This script populates that mirror from a source (HTTP URLs or another
S3 bucket), validates each tile, and emits a manifest so the running stack
knows what's actually available.

Subcommands:

    list      Emit the SRTM-style tile names a bbox/region needs.
    ingest    Download from a source and upload to the destination bucket,
              validating each tile and writing a manifest.json.
    verify    Walk the destination bucket and report missing/corrupt tiles.

Examples
--------

# Print every tile name covering Brazil at 1°×1°.
python utils/mirror_terrain.py list --bbox -34,-74,6,-32

# Ingest FABDEM tiles for São Paulo state from an HTTP base URL into S3.
python utils/mirror_terrain.py ingest \\
    --bbox -25,-53,-19,-44 \\
    --source-url "https://example.org/fabdem/{tile}_FABDEM_V1-2.tif" \\
    --dest-bucket my-terrain-mirror \\
    --dest-prefix fabdem-v1-2 \\
    --dataset fabdem

# Verify a canopy mirror against an expected bbox.
python utils/mirror_terrain.py verify \\
    --bbox -25,-53,-19,-44 \\
    --dest-bucket my-canopy-mirror \\
    --dest-prefix lang2023 \\
    --dataset lang2023

The script does not run inside the FastAPI process — it's an offline helper.
It only depends on boto3 + requests + (optionally) rasterio for deep
validation. If rasterio isn't installed it falls back to byte-level checks.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import io
import json
import logging
import os
import sys
import time
from typing import Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger("mirror_terrain")

# Default filename templates per dataset. Operators can override on the CLI.
DATASET_TEMPLATES = {
    "fabdem": "{tile}_FABDEM_V1-2.tif",
    "copernicus": "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif",
    "lang2023": "{tile}.tif",
    "mapbiomas": "mapbiomas_{tile}.tif",
    "custom": "{tile}.tif",
}

# Sentinel for "no upper bound" elevation check.
ELEVATION_PLAUSIBILITY = {
    # DTMs (bare ground) — Everest is ~8848 m. 9000 m gives slack.
    "fabdem": (-500.0, 9000.0),
    "copernicus": (-500.0, 9000.0),
    # Canopy datasets — tallest tree is ~115 m. 200 m clamps wild outliers.
    "lang2023": (0.0, 200.0),
    "mapbiomas": (0.0, 200.0),
    "custom": (-500.0, 9000.0),
}


# ---------------------------------------------------------------------------
# Tile naming
# ---------------------------------------------------------------------------


def tile_name_for(lat: int, lon: int) -> str:
    """SRTM-style 1°×1° tile name for the SW corner at (lat, lon)."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"


def tiles_in_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list[str]:
    """Enumerate every 1°×1° tile that intersects the bbox."""
    if min_lat > max_lat or min_lon > max_lon:
        raise ValueError("bbox must be (min_lat, min_lon, max_lat, max_lon) with min < max")
    lat_lo = int(min_lat) if min_lat == int(min_lat) else int(min_lat) - (1 if min_lat < 0 else 0)
    lat_hi = int(max_lat) if max_lat == int(max_lat) else int(max_lat) + (0 if max_lat < 0 else 1)
    lon_lo = int(min_lon) if min_lon == int(min_lon) else int(min_lon) - (1 if min_lon < 0 else 0)
    lon_hi = int(max_lon) if max_lon == int(max_lon) else int(max_lon) + (0 if max_lon < 0 else 1)
    out = []
    for lat in range(lat_lo, lat_hi):
        for lon in range(lon_lo, lon_hi):
            out.append(tile_name_for(lat, lon))
    return out


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be 'min_lat,min_lon,max_lat,max_lon'")
    return tuple(float(p) for p in parts)  # type: ignore[return-value]


def filename_for(tile: str, template: str) -> str:
    """Apply a filename template to an SRTM-style tile name."""
    ns, ew = tile[0], tile[3]
    lat = int(tile[1:3])
    lon = int(tile[4:7])
    return template.format(tile=tile, ns=ns, ew=ew, lat=lat, lon=lon)


# ---------------------------------------------------------------------------
# Tile validation
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ValidationResult:
    ok: bool
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    elevation_min: Optional[float] = None
    elevation_max: Optional[float] = None
    error: Optional[str] = None


def validate_tile_bytes(payload: bytes, dataset: str, deep: bool = True) -> ValidationResult:
    """Sanity-check a downloaded tile.

    Cheap checks always run (size, GeoTIFF magic). Deep checks (raster open,
    elevation range) require rasterio; if it's missing we skip them and
    return a partial result rather than failing.
    """
    if len(payload) < 256:
        return ValidationResult(ok=False, size_bytes=len(payload), error="tile is suspiciously small (< 256 bytes)")
    # GeoTIFF magic: little-endian 'II' + 42, or big-endian 'MM' + 42.
    head = payload[:4]
    if not (head[:2] in (b"II", b"MM")):
        return ValidationResult(ok=False, size_bytes=len(payload), error="not a TIFF (bad magic)")

    if not deep:
        return ValidationResult(ok=True, size_bytes=len(payload))

    try:
        import rasterio  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        logger.debug("rasterio/numpy unavailable; skipping deep validation")
        return ValidationResult(ok=True, size_bytes=len(payload))

    try:
        with rasterio.MemoryFile(payload) as memfile:
            with memfile.open() as src:
                width, height = src.width, src.height
                # Sample a small window — full reads of 1°×1° canopy tiles can be
                # 100s of MB and we just want a plausibility check.
                window = rasterio.windows.Window(
                    col_off=0, row_off=0,
                    width=min(512, width), height=min(512, height),
                )
                arr = src.read(1, window=window)
                src_nodata = src.nodata
                if src_nodata is not None:
                    arr = arr[arr != src_nodata]
                if arr.size == 0:
                    return ValidationResult(
                        ok=True, size_bytes=len(payload),
                        width=width, height=height,
                        error="window all-nodata (acceptable but worth noting)",
                    )
                emin, emax = float(np.nanmin(arr)), float(np.nanmax(arr))
                lo, hi = ELEVATION_PLAUSIBILITY.get(dataset, (-1e9, 1e9))
                if emin < lo or emax > hi:
                    return ValidationResult(
                        ok=False, size_bytes=len(payload),
                        width=width, height=height,
                        elevation_min=emin, elevation_max=emax,
                        error=f"elevation range [{emin:.1f}, {emax:.1f}] outside plausible [{lo}, {hi}] for {dataset}",
                    )
                return ValidationResult(
                    ok=True, size_bytes=len(payload),
                    width=width, height=height,
                    elevation_min=emin, elevation_max=emax,
                )
    except Exception as e:  # pragma: no cover — depends on rasterio internals
        return ValidationResult(ok=False, size_bytes=len(payload), error=f"rasterio open failed: {e}")


# ---------------------------------------------------------------------------
# Source loaders
# ---------------------------------------------------------------------------


class HttpSource:
    """Pull tiles from a URL template like 'https://.../{tile}_FABDEM_V1-2.tif'."""

    def __init__(self, url_template: str, timeout: float = 60.0):
        self.url_template = url_template
        self.timeout = timeout
        # Lazy import — keeps `list` subcommand usable without requests.
        import requests  # type: ignore
        self._session = requests.Session()

    def fetch(self, tile: str) -> Optional[bytes]:
        url = filename_for(tile, self.url_template) if "{" in self.url_template else self.url_template.replace("{tile}", tile)
        try:
            resp = self._session.get(url, timeout=self.timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            logger.warning(f"fetch failed for {tile} at {url}: {e}")
            return None


class S3Source:
    """Pull tiles from another S3 bucket (e.g., a public mirror you have access to)."""

    def __init__(self, bucket: str, key_template: str, anonymous: bool = False):
        import boto3  # type: ignore
        from botocore import UNSIGNED  # type: ignore
        from botocore.config import Config  # type: ignore

        cfg = Config(signature_version=UNSIGNED) if anonymous else None
        self.s3 = boto3.client("s3", config=cfg)
        self.bucket = bucket
        self.key_template = key_template

    def fetch(self, tile: str) -> Optional[bytes]:
        from botocore.exceptions import ClientError  # type: ignore
        key = filename_for(tile, self.key_template)
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                return None
            raise


class LocalSource:
    """Pull tiles from a local directory (useful for offline ingestion)."""

    def __init__(self, root: str, filename_template: str):
        self.root = root
        self.filename_template = filename_template

    def fetch(self, tile: str) -> Optional[bytes]:
        path = os.path.join(self.root, filename_for(tile, self.filename_template))
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read()


def make_source(args) -> object:
    if args.source_url:
        return HttpSource(args.source_url)
    if args.source_bucket:
        template = args.source_key_template or DATASET_TEMPLATES[args.dataset]
        return S3Source(
            bucket=args.source_bucket,
            key_template=template,
            anonymous=args.source_anonymous,
        )
    if args.source_dir:
        template = args.source_filename_template or DATASET_TEMPLATES[args.dataset]
        return LocalSource(root=args.source_dir, filename_template=template)
    raise SystemExit("Need exactly one of --source-url, --source-bucket, --source-dir")


# ---------------------------------------------------------------------------
# Destination (S3 mirror)
# ---------------------------------------------------------------------------


class DestinationBucket:
    def __init__(self, bucket: str, prefix: str, key_template: str):
        import boto3  # type: ignore
        self.s3 = boto3.client("s3")
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.key_template = key_template

    def key_for(self, tile: str) -> str:
        fname = filename_for(tile, self.key_template)
        return f"{self.prefix}/{fname}" if self.prefix else fname

    def exists(self, tile: str) -> bool:
        from botocore.exceptions import ClientError  # type: ignore
        try:
            self.s3.head_object(Bucket=self.bucket, Key=self.key_for(tile))
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def head(self, tile: str) -> Optional[dict]:
        from botocore.exceptions import ClientError  # type: ignore
        try:
            return self.s3.head_object(Bucket=self.bucket, Key=self.key_for(tile))
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise

    def put(self, tile: str, payload: bytes, content_type: str = "image/tiff") -> None:
        self.s3.put_object(
            Bucket=self.bucket,
            Key=self.key_for(tile),
            Body=payload,
            ContentType=content_type,
        )

    def get(self, tile: str) -> Optional[bytes]:
        from botocore.exceptions import ClientError  # type: ignore
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=self.key_for(tile))
            return obj["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(args) -> int:
    tiles = tiles_in_bbox(*args.bbox)
    for t in tiles:
        print(t)
    print(f"# total: {len(tiles)} tiles", file=sys.stderr)
    return 0


def cmd_ingest(args) -> int:
    tiles = tiles_in_bbox(*args.bbox)
    template = args.dest_key_template or DATASET_TEMPLATES[args.dataset]

    src = make_source(args)
    dst = DestinationBucket(args.dest_bucket, args.dest_prefix, template)

    manifest_entries: list[dict] = []
    skipped = uploaded = missing_in_source = invalid = 0
    started = time.time()

    for i, tile in enumerate(tiles, 1):
        prefix = f"[{i}/{len(tiles)}] {tile}"
        if not args.force and dst.exists(tile):
            logger.info(f"{prefix}: already in destination, skipping")
            skipped += 1
            continue

        payload = src.fetch(tile)  # type: ignore[attr-defined]
        if payload is None:
            logger.info(f"{prefix}: not found in source")
            missing_in_source += 1
            continue

        result = validate_tile_bytes(payload, args.dataset, deep=not args.no_deep_validation)
        if not result.ok:
            logger.warning(f"{prefix}: invalid — {result.error}")
            invalid += 1
            if not args.allow_invalid:
                continue

        if args.dry_run:
            logger.info(f"{prefix}: would upload {result.size_bytes} bytes (dry-run)")
        else:
            dst.put(tile, payload)
            logger.info(f"{prefix}: uploaded {result.size_bytes} bytes")
        uploaded += 1
        manifest_entries.append({
            "tile": tile,
            "key": dst.key_for(tile),
            "size_bytes": result.size_bytes,
            "width": result.width,
            "height": result.height,
            "elevation_min": result.elevation_min,
            "elevation_max": result.elevation_max,
            "uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })

    elapsed = time.time() - started
    summary = {
        "dataset": args.dataset,
        "bbox": list(args.bbox),
        "destination": {
            "bucket": args.dest_bucket,
            "prefix": args.dest_prefix,
            "key_template": template,
        },
        "tile_count": len(tiles),
        "uploaded": uploaded,
        "skipped": skipped,
        "missing_in_source": missing_in_source,
        "invalid": invalid,
        "elapsed_seconds": round(elapsed, 1),
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tiles": manifest_entries,
    }

    manifest_path = args.manifest or f"manifest-{args.dataset}-{int(time.time())}.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"wrote manifest to {manifest_path}")

    if not args.dry_run and args.upload_manifest:
        manifest_key = f"{args.dest_prefix.rstrip('/')}/manifest.json" if args.dest_prefix else "manifest.json"
        with open(manifest_path, "rb") as f:
            dst.s3.put_object(Bucket=args.dest_bucket, Key=manifest_key,
                              Body=f.read(), ContentType="application/json")
        logger.info(f"uploaded manifest to s3://{args.dest_bucket}/{manifest_key}")

    print(json.dumps({k: v for k, v in summary.items() if k != "tiles"}, indent=2))
    return 0 if invalid == 0 or args.allow_invalid else 1


def cmd_verify(args) -> int:
    tiles = tiles_in_bbox(*args.bbox)
    template = args.dest_key_template or DATASET_TEMPLATES[args.dataset]
    dst = DestinationBucket(args.dest_bucket, args.dest_prefix, template)

    missing: list[str] = []
    invalid: list[tuple[str, str]] = []
    ok = 0

    for tile in tiles:
        head = dst.head(tile)
        if head is None:
            missing.append(tile)
            continue
        if args.deep:
            payload = dst.get(tile)
            if payload is None:
                missing.append(tile)
                continue
            result = validate_tile_bytes(payload, args.dataset, deep=True)
            if not result.ok:
                invalid.append((tile, result.error or "unknown"))
                continue
        ok += 1

    report = {
        "dataset": args.dataset,
        "bbox": list(args.bbox),
        "tile_count": len(tiles),
        "present": ok,
        "missing": missing,
        "invalid": [{"tile": t, "reason": r} for t, r in invalid],
    }
    print(json.dumps(report, indent=2))
    return 0 if not missing and not invalid else 1


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _add_bbox(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--bbox", required=True, type=parse_bbox,
        help="bounding box 'min_lat,min_lon,max_lat,max_lon'",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mirror FABDEM/canopy tiles into an operator-hosted S3 bucket.")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="Enumerate tiles covering a bbox.")
    _add_bbox(p_list)
    p_list.set_defaults(func=cmd_list)

    p_ing = sub.add_parser("ingest", help="Download from source, validate, upload to destination.")
    _add_bbox(p_ing)
    p_ing.add_argument("--dataset", required=True, choices=sorted(DATASET_TEMPLATES.keys()))
    p_ing.add_argument("--source-url", help="HTTP URL template, e.g. 'https://host/{tile}_FABDEM_V1-2.tif'")
    p_ing.add_argument("--source-bucket", help="S3 bucket to pull tiles from")
    p_ing.add_argument("--source-key-template", help="Override key template for --source-bucket")
    p_ing.add_argument("--source-anonymous", action="store_true", help="Use unsigned access for --source-bucket")
    p_ing.add_argument("--source-dir", help="Local directory to pull tiles from")
    p_ing.add_argument("--source-filename-template", help="Override template for --source-dir")
    p_ing.add_argument("--dest-bucket", required=True, help="Destination S3 bucket (your operator mirror)")
    p_ing.add_argument("--dest-prefix", default="", help="Prefix inside the destination bucket")
    p_ing.add_argument("--dest-key-template", help="Filename template inside the destination prefix")
    p_ing.add_argument("--manifest", help="Path for the local manifest.json output")
    p_ing.add_argument("--upload-manifest", action="store_true", help="Also upload manifest.json to the destination prefix")
    p_ing.add_argument("--force", action="store_true", help="Re-upload even if a tile already exists in the destination")
    p_ing.add_argument("--dry-run", action="store_true", help="Skip the actual upload step")
    p_ing.add_argument("--no-deep-validation", action="store_true", help="Skip rasterio-based validation (faster, less safe)")
    p_ing.add_argument("--allow-invalid", action="store_true", help="Upload tiles even if validation fails")
    p_ing.set_defaults(func=cmd_ingest)

    p_ver = sub.add_parser("verify", help="Walk the destination bucket and report missing/corrupt tiles.")
    _add_bbox(p_ver)
    p_ver.add_argument("--dataset", required=True, choices=sorted(DATASET_TEMPLATES.keys()))
    p_ver.add_argument("--dest-bucket", required=True)
    p_ver.add_argument("--dest-prefix", default="")
    p_ver.add_argument("--dest-key-template")
    p_ver.add_argument("--deep", action="store_true", help="Also download and validate each tile (slow)")
    p_ver.set_defaults(func=cmd_verify)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(message)s")
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
