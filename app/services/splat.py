import gzip
import logging
import math
import os
import io
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from typing import Literal, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from rasterio.transform import Affine

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from diskcache import Cache

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from PIL import Image

from app.models.CoveragePredictionRequest import CoveragePredictionRequest
from app.services.engine import PropagationEngine
from app.services.clutter import ClutterSource
from app.services.geotiff_utils import ppm_kml_to_geotiff
from app.redis_config import DB_SRTM_CACHE, get_redis_client
from app.metrics import (
    inc,
    splat_subprocess_duration_seconds,
    srtm_cache_events_total,
)


logger = logging.getLogger(__name__)

# Redis HGT tile cache shared across workers; survives diskcache LRU eviction.
# Set REDIS_SRTM_CACHE_TTL=0 to disable persistence-side caching.
SRTM_REDIS_TTL = int(os.environ.get("REDIS_SRTM_CACHE_TTL", str(7 * 24 * 3600)))
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("s3transfer").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# Supported DEM sources. Each entry maps to a default S3 bucket/prefix for tile
# downloads. The class transcodes non-SRTM sources into SRTM-style .hgt.gz bytes
# so the rest of the SPLAT! pipeline (srtm2sdf, splat, splat-hd) is unchanged.
DEM_SOURCES = {
    "srtm": {
        "bucket": "elevation-tiles-prod",
        "prefix": "v2/skadi",
    },
    "copernicus": {
        # Copernicus GLO-30 (DSM, ~30 m). COG GeoTIFFs, 1°×1° tiles.
        # Open data registry: https://registry.opendata.aws/copernicus-dem/
        "bucket": "copernicus-dem-30m",
        "prefix": "",
    },
    "fabdem": {
        # FABDEM (Hawker et al., 2022) — Copernicus DEM with canopy/buildings
        # removed, i.e. a true DTM. Distributed at https://data.bris.ac.uk/data/
        # under CC BY-NC-SA 4.0. There is no public AWS Open Data mirror, so
        # operators must host their own bucket and configure FABDEM_BUCKET /
        # FABDEM_PREFIX. Defaults below assume an S3-compatible mirror you control.
        "bucket": os.environ.get("FABDEM_BUCKET", ""),
        "prefix": os.environ.get("FABDEM_PREFIX", ""),
    },
}

# When a FABDEM tile is missing (ocean, gap, mirror not yet populated), fall
# back to this source. Empty string disables the fallback (raises).
FABDEM_FALLBACK_SOURCE = os.environ.get("FABDEM_FALLBACK_SOURCE", "copernicus")

# FABDEM filename pattern. The official V1.2 release uses
# `N35W120_FABDEM_V1-2.tif`. Operators on a different version override this.
FABDEM_FILENAME_TEMPLATE = os.environ.get(
    "FABDEM_FILENAME_TEMPLATE", "{ns}{lat:02d}{ew}{lon:03d}_FABDEM_V1-2.tif"
)


class Splat(PropagationEngine):
    def __init__(
        self,
        splat_path: str,
        cache_dir: str = ".splat_tiles",
        cache_size_gb: float = 1.0,
        bucket_name: str | None = None,
        bucket_prefix: str | None = None,
        dem_source: str | None = None,
        clutter_source: ClutterSource | None = None,
    ):
        """
        SPLAT! wrapper class. Provides methods for generating SPLAT! RF coverage maps in GeoTIFF format.
        This class automatically downloads and caches the necessary terrain data from AWS:
        https://registry.opendata.aws/terrain-tiles/.

        SPLAT! and its optional utilities (splat, splat-hd, srtm2sdf, srtm2sdf-hd) must be installed
        in the `splat_path` directory and be executable.

        See the SPLAT! documentation: https://www.qsl.net/kd2bd/splat.html
        Additional details: https://github.com/jmcmellen/splat

        Args:
            splat_path (str): Path to the directory containing the SPLAT! binaries.
            cache_dir (str): Directory to store cached terrain tiles.
            cache_size_gb (float): Maximum size of the cache in gigabytes (GB). Defaults to 1.0.
                When the size of the cached tiles exceeds this value, the oldest tiles are deleted
                and will be re-downloaded as required.
            bucket_name (str | None): Override S3 bucket for terrain tiles. If None, uses the
                default for the selected `dem_source`.
            bucket_prefix (str | None): Override S3 prefix for terrain tiles. If None, uses the
                default for the selected `dem_source`.
            dem_source (str | None): Elevation data source. One of: "srtm" (default — NASA SRTM
                1-arcsec via `elevation-tiles-prod`) or "copernicus" (Copernicus GLO-30 DSM via
                `copernicus-dem-30m`). Defaults to env var DEM_SOURCE or "srtm".
        """

        resolved_source = (dem_source or os.environ.get("DEM_SOURCE", "srtm")).lower().strip()
        if resolved_source not in DEM_SOURCES:
            raise ValueError(
                f"Unknown DEM source '{resolved_source}'. "
                f"Supported: {sorted(DEM_SOURCES.keys())}"
            )
        self.dem_source = resolved_source
        self.clutter_source = clutter_source
        source_defaults = DEM_SOURCES[resolved_source]

        # Check the provided SPLAT! path exists
        if not os.path.isdir(splat_path):
            raise FileNotFoundError(
                f"Provided SPLAT! path '{splat_path}' is not a valid directory."
            )

        # SPLAT! binaries
        self.splat_binary = os.path.join(splat_path, "splat")  # core SPLAT! program
        self.splat_hd_binary = os.path.join(
            splat_path, "splat-hd"
        )  # used instead of the splat binary when using the 1-arcsecond / 30 meter resolution terrain data.
        self.srtm2sdf_binary = os.path.join(
            splat_path, "srtm2sdf"
        )  # convert 3-arcsecond resolution srtm .hgt terrain tiles to SPLAT! .sdf terrain tiles.
        self.srtm2sdf_hd_binary = os.path.join(
            splat_path, "srtm2sdf-hd"
        )  # used instead of srtm2sdf when using the 1-arcsecond / 30 meter resolution terrain data.

        # Check the SPLAT! binaries exist and are executable
        if not os.path.isfile(self.splat_binary) or not os.access(
            self.splat_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'splat' binary not found or not executable at '{self.splat_binary}'"
            )
        if not os.path.isfile(self.splat_hd_binary) or not os.access(
            self.splat_hd_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'splat-hd' binary not found or not executable at '{self.splat_hd_binary}'"
            )
        if not os.path.isfile(self.srtm2sdf_binary) or not os.access(
            self.srtm2sdf_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'srtm2sdf_binary' binary not found or not executable at '{self.srtm2sdf_binary}'"
            )
        if not os.path.isfile(self.srtm2sdf_hd_binary) or not os.access(
            self.srtm2sdf_hd_binary, os.X_OK
        ):
            raise FileNotFoundError(
                f"'srtm2sdf_hd_binary' binary not found or not executable at '{self.srtm2sdf_hd_binary}'"
            )

        self.tile_cache = Cache(
            cache_dir, size_limit=int(cache_size_gb * 1024 * 1024 * 1024)
        )

        try:
            self._redis_tile_cache = get_redis_client(db=DB_SRTM_CACHE)
            self._redis_tile_cache.ping()
        except Exception as e:
            logger.warning(f"Redis SRTM tile cache unavailable, falling back to disk only: {e}")
            self._redis_tile_cache = None

        # Tunable boto3 client: larger pool + adaptive retry. The pool size
        # has to match SPLAT_DOWNLOAD_WORKERS so the threadpool above doesn't
        # serialize on a connection. Default 16 mirrors the download phase.
        s3_pool = int(os.environ.get("SPLAT_DOWNLOAD_WORKERS", "16"))
        s3_config = Config(
            signature_version=UNSIGNED,
            max_pool_connections=max(s3_pool, 10),
            retries={"max_attempts": 5, "mode": "adaptive"},
        )
        self.s3 = boto3.client("s3", config=s3_config)
        self.bucket_name = bucket_name if bucket_name is not None else source_defaults["bucket"]
        self.bucket_prefix = bucket_prefix if bucket_prefix is not None else source_defaults["prefix"]

        logger.info(
            f"Initialized SPLAT! with terrain tile cache at '{cache_dir}' "
            f"(size limit {cache_size_gb} GB, dem_source={self.dem_source}, "
            f"bucket={self.bucket_name}/{self.bucket_prefix or '<root>'})."
        )

    # ------------------------------------------------------------------
    # Cache-key helpers (namespaced by DEM source + clutter source so tiles
    # from different terrain/clutter combinations never collide)
    # ------------------------------------------------------------------
    @property
    def _cache_namespace(self) -> str:
        """Cache namespace combining DEM source, clutter source and factor.

        When clutter is disabled, the namespace is just the DEM source — this
        keeps existing caches valid when no clutter override is configured.

        When clutter is on, the penetration factor is folded into the
        namespace because it scales the canopy heights baked into each cached
        tile. Two requests with different factors must NOT share tiles.
        """
        if self.clutter_source is None:
            return self.dem_source
        # Quantize the factor to 2 decimals so 0.6 and 0.6000001 share a key
        # (the factor only matters to ~0.05 anyway — calibration noise floor).
        factor = round(self.clutter_source.penetration_factor, 2)
        return f"{self.dem_source}+{self.clutter_source.name}@{factor:.2f}"

    def _disk_key(self, name: str) -> str:
        """Disk LRU key — namespaced by DEM + clutter source."""
        return f"{self._cache_namespace}:{name}"

    def tile_redis_key(self, tile_name: str) -> str:
        """Redis HGT cache key — namespaced by DEM + clutter source."""
        return f"dem:{self._cache_namespace}:hgt:{tile_name}"

    def _sdf_redis_key(self, sdf_filename: str) -> str:
        return f"dem:{self._cache_namespace}:sdf:{sdf_filename}"

    @property
    def name(self) -> str:
        return "splat"

    def is_available(self) -> bool:
        return (
            os.path.isfile(self.splat_binary) and os.access(self.splat_binary, os.X_OK) and
            os.path.isfile(self.splat_hd_binary) and os.access(self.splat_hd_binary, os.X_OK)
        )

    def _report_progress(self, task_id: str | None, stage: str, progress: float, detail: str = "") -> None:
        """Write progress data to Redis for SSE streaming."""
        if not task_id:
            return
        try:
            import json
            r = get_redis_client()
            r.setex(f"{task_id}:progress", 3600, json.dumps({
                "stage": stage,
                "progress": round(progress, 2),
                "detail": detail,
            }))
        except Exception as e:
            logger.debug(f"Failed to report progress for {task_id}: {e}")

    def coverage_prediction(self, request: CoveragePredictionRequest, *, task_id: str | None = None) -> bytes:
        """
        Execute a SPLAT! coverage prediction using the provided CoveragePredictionRequest.

        Args:
            request (CoveragePredictionRequest): The coverage prediction request object.
            task_id: Optional task ID for progress reporting via Redis.

        Returns:
            bytes: the SPLAT! coverage prediction as a GeoTIFF.

        Raises:
            RuntimeError: If SPLAT! fails to execute.
        """
        logger.debug(f"Coverage prediction request: {request.json()}")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                logger.debug(f"Temporary directory created: {tmpdir}")

                # FIXME: Eventually support high-resolution terrain data
                request.high_resolution = False

                # Configurable radius cap (MAXPAGES=225 supports ~810km at equator, ~600km at lat 50)
                max_radius_m = int(os.environ.get("MAX_SIMULATION_RADIUS_KM", "600")) * 1000
                if request.radius > max_radius_m:
                    logger.warning(f"Radius {request.radius}m exceeds limit, clamping to {max_radius_m}m.")
                    request.radius = max_radius_m

                # determine the required terrain tiles
                required_tiles = Splat._calculate_required_terrain_tiles(request.lat, request.lon, request.radius)
                total_tiles = len(required_tiles)

                self._report_progress(task_id, "downloading_tiles", 0.05, f"0/{total_tiles} tiles")

                # Two-phase pipeline:
                #   Phase 1: download all HGT tiles in parallel (I/O-bound; high
                #            concurrency works well against S3).
                #   Phase 2: convert HGT -> SDF in parallel (CPU-bound; cap at
                #            cpu_count to avoid GIL/disk thrashing).
                # When tiles are already cached the I/O phase is near-zero; when
                # SDFs are cached the CPU phase is near-zero. Splitting also makes
                # progress reporting more accurate.
                cpu_count = max(1, (os.cpu_count() or 4))
                download_workers = min(len(required_tiles),
                                       int(os.environ.get("SPLAT_DOWNLOAD_WORKERS", "16")))
                convert_workers = min(len(required_tiles),
                                      int(os.environ.get("SPLAT_CONVERT_WORKERS", str(cpu_count))))

                completed = 0
                with ThreadPoolExecutor(max_workers=download_workers) as dl_pool:
                    download_futures = {
                        dl_pool.submit(self._download_terrain_tile, tile_name): (
                            tile_name, sdf_name, sdf_hd_name
                        )
                        for tile_name, sdf_name, sdf_hd_name in required_tiles
                    }
                    downloaded: list[tuple[bytes, str, str, str]] = []
                    for future in as_completed(download_futures):
                        tile_name, sdf_name, sdf_hd_name = download_futures[future]
                        downloaded.append((future.result(), tile_name, sdf_name, sdf_hd_name))
                        completed += 1
                        # I/O accounts for ~12% of the [0.05, 0.30] window.
                        self._report_progress(task_id, "downloading_tiles",
                                              0.05 + (completed / total_tiles) * 0.12,
                                              f"{completed}/{total_tiles} downloaded")

                self._report_progress(task_id, "converting_tiles", 0.17,
                                      f"0/{total_tiles} converted")

                completed = 0
                with ThreadPoolExecutor(max_workers=convert_workers) as conv_pool:
                    convert_futures = {
                        conv_pool.submit(
                            self._convert_and_write_sdf,
                            tile_data, tile_name, sdf_name, sdf_hd_name,
                            request.high_resolution, tmpdir,
                        ): tile_name
                        for tile_data, tile_name, sdf_name, sdf_hd_name in downloaded
                    }
                    for future in as_completed(convert_futures):
                        future.result()
                        completed += 1
                        self._report_progress(task_id, "converting_tiles",
                                              0.17 + (completed / total_tiles) * 0.13,
                                              f"{completed}/{total_tiles} converted")

                self._report_progress(task_id, "configuring", 0.35, "Writing model parameters")

                # write transmitter / qth file
                with open(os.path.join(tmpdir, "tx.qth"), "wb") as qth_file:
                    qth_file.write(Splat._create_splat_qth("tx",request.lat,request.lon,request.tx_height))

                # write model parameter / lrp file
                with open(os.path.join(tmpdir,"splat.lrp"), "wb") as lrp_file:
                    lrp_file.write(Splat._create_splat_lrp(
                        ground_dielectric=request.ground_dielectric,
                        ground_conductivity=request.ground_conductivity,
                        atmosphere_bending=request.atmosphere_bending,
                        frequency_mhz=request.frequency_mhz,
                        radio_climate=request.radio_climate,
                        polarization=request.polarization,
                        situation_fraction=request.situation_fraction,
                        time_fraction=request.time_fraction,
                        tx_power=request.tx_power,
                        tx_gain=request.tx_gain,
                        system_loss=request.system_loss))

                # write colorbar / dcf file (grayscale — colormap applied client-side)
                with open(os.path.join(tmpdir, "splat.dcf"), "wb") as dcf_file:
                    dcf_file.write(Splat._create_splat_dcf())

                logger.debug(f"Contents of {tmpdir}: {os.listdir(tmpdir)}")

                self._report_progress(task_id, "running_splat", 0.40, "Starting SPLAT! simulation")

                splat_command = [
                    (
                        self.splat_hd_binary
                        if request.high_resolution
                        else self.splat_binary
                    ),
                    "-t",
                    "tx.qth",
                    "-L",
                    str(request.rx_height),
                    "-metric",
                    "-R",
                    str(request.radius / 1000.0),
                    "-sc",
                ]
                # When spatial clutter is active, vegetation is already baked
                # into the SDF as synthetic terrain — adding `-gc` on top would
                # double-count the obstruction. Skip the uniform knob.
                if self.clutter_source is None:
                    splat_command += ["-gc", str(request.clutter_height)]
                splat_command += [
                    "-ngs",
                    "-N",
                    "-o",
                    "output.ppm",
                    "-dbm",
                    "-db",
                    str(request.signal_threshold),
                    "-kml",
                    "-olditm",
                ]
                # flag "olditm" uses the standard ITM model instead of ITWOM, which has produced unrealistic results.
                logger.debug(f"Executing SPLAT! command: {' '.join(splat_command)}")

                splat_binary_label = "splat-hd" if request.high_resolution else "splat"
                splat_subprocess_start = time.perf_counter()
                splat_result = subprocess.run(
                    splat_command,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if splat_subprocess_duration_seconds is not None:
                    try:
                        splat_subprocess_duration_seconds.labels(
                            binary=splat_binary_label
                        ).observe(time.perf_counter() - splat_subprocess_start)
                    except Exception:
                        pass

                logger.debug(f"SPLAT! stdout:\n{splat_result.stdout}")
                logger.debug(f"SPLAT! stderr:\n{splat_result.stderr}")

                if splat_result.returncode != 0:
                    logger.error(
                        f"SPLAT! execution failed with return code {splat_result.returncode}"
                    )
                    raise RuntimeError(
                        f"SPLAT! execution failed with return code {splat_result.returncode}\n"
                        f"Stdout: {splat_result.stdout}\nStderr: {splat_result.stderr}"
                    )

                self._report_progress(task_id, "converting", 0.90, "Generating GeoTIFF")

                with open(os.path.join(tmpdir, "output.ppm"), "rb") as ppm_file:
                    with open(os.path.join(tmpdir, "output.kml"), "rb") as kml_file:
                        ppm_data = ppm_file.read()
                        kml_data = kml_file.read()
                        geotiff_data = ppm_kml_to_geotiff(ppm_data, kml_data)

                self._report_progress(task_id, "completed", 1.0)

                logger.info("SPLAT! coverage prediction completed successfully.")
                return geotiff_data

            except Exception as e:
                logger.error(f"Error during coverage prediction: {e}")
                raise RuntimeError(f"Error during coverage prediction: {e}")

    def _download_and_convert_tile(self, tile_name: str, sdf_name: str, sdf_hd_name: str,
                                    high_resolution: bool, tmpdir: str) -> None:
        """Download a terrain tile, convert to SDF, and write to tmpdir.

        Kept for backward compatibility; new code uses the two-phase pipeline
        with _download_terrain_tile + _convert_and_write_sdf.
        """
        tile_data = self._download_terrain_tile(tile_name)
        self._convert_and_write_sdf(tile_data, tile_name, sdf_name, sdf_hd_name,
                                    high_resolution, tmpdir)

    def _convert_and_write_sdf(self, tile_data: bytes, tile_name: str,
                               sdf_name: str, sdf_hd_name: str,
                               high_resolution: bool, tmpdir: str) -> None:
        """Convert a downloaded HGT to SDF and write it to tmpdir."""
        sdf_data = self._convert_hgt_to_sdf(tile_data, tile_name, high_resolution=high_resolution)
        target = sdf_hd_name if high_resolution else sdf_name
        with open(os.path.join(tmpdir, target), "wb") as f:
            f.write(sdf_data)

    @staticmethod
    def _calculate_required_terrain_tiles(
            lat: float, lon: float, radius: float
    ) -> List[Tuple[str, str, str]]:
        """
        Determine the set of required terrain tiles for the specified area and their corresponding .sdf / -hd.sdf
        filenames. This is used for downloading terrain data for SPLAT! which requires the files to follow a specific
        naming convention.

        Calculates the geographic bounding box based on the provided latitude, longitude, and radius, then
        determines the necessary tiles to cover the area. It returns filenames in the following formats:

            - .hgt.gz files: raw 1 arc-second terrain elevation tiles stored in AWS Open Data / S3.
            - .sdf files: Used for standard resolution (3-arcsecond) terrain data in SPLAT!.
            - .sdf-hd files: Used for high-resolution (1-arcsecond) terrain data in SPLAT!.

        The .hgt.gz filenames have the format:
            <N|S><latitude: 2 digits><E|W><longitude: 3 digits>.hgt.gz
            Example: N35W120.hgt.gz

        The .sdf and .sdf-hd filenames have the format:
            <lat_start>:<lat_end>:<lon_start>:<lon_end>.sdf
            <lat_start>:<lat_end>:<lon_start>:<lon_end>-hd.sdf
            Example: 35:36:-120:-119.sdf, 35:36:-120:-119-hd.sdf

        Args:
            lat (float): Latitude of the center point in degrees.
            lon (float): Longitude of the center point in degrees.
            radius (float): Simulation coverage radius in meters.

        Returns:
            List[Tuple[str, str, str]]: A list of tuples, each containing:
                - .hgt.gz filename (str)
                - Corresponding .sdf filename (str)
                - Corresponding .sdf-hd filename (str)
        """

        earth_radius = 6378137  # meters, approximate.

        # Convert radius to angular distance in degrees
        delta_deg = (radius / earth_radius) * (180 / math.pi)

        # Compute bounding box in degrees
        lat_min = lat - delta_deg
        lat_max = lat + delta_deg
        lon_min = lon - delta_deg / math.cos(math.radians(lat))
        lon_max = lon + delta_deg / math.cos(math.radians(lat))

        # Determine tile boundaries (rounded to 1-degree tiles)
        lat_min_tile = math.floor(lat_min)
        lat_max_tile = math.floor(lat_max)
        lon_min_tile = math.floor(lon_min)
        lon_max_tile = math.floor(lon_max)

        # All tile names within the bounding box
        tile_names = []

        for lat_tile in range(lat_min_tile, lat_max_tile + 1):
            for lon_tile in range(lon_min_tile, lon_max_tile + 1):
                ns = "N" if lat_tile >= 0 else "S"
                ew = "E" if lon_tile >= 0 else "W"
                tile_name = f"{ns}{abs(lat_tile):02d}{ew}{abs(lon_tile):03d}.hgt.gz"

                # .sdf file boundaries
                lat_start = lat_tile
                lon_start = lon_tile
                lat_end = lat_start + 1
                lon_end = lon_start + 1

                # Generate .sdf file names
                sdf_filename = Splat._hgt_filename_to_sdf_filename(tile_name, high_resolution = False)
                sdf_hd_filename = Splat._hgt_filename_to_sdf_filename(tile_name, high_resolution = True)
                tile_names.append((tile_name, sdf_filename, sdf_hd_filename))

        logger.debug("required tile names are: ")
        logger.debug(tile_names)
        return tile_names

    @staticmethod
    def _create_splat_qth(name: str, latitude: float, longitude: float, elevation: float) -> bytes:
        """
        Generate the contents of a SPLAT! .qth file describing a transmitter or receiver site.

        Args:
            name (str): Name of the site (unused but required for SPLAT!).
            latitude (float): Latitude of the site in degrees.
            longitude (float): Longitude of the site in degrees.
            elevation (float): Elevation (AGL) of the site in meters.

        Returns:
            bytes: The content of the .qth file formatted for SPLAT!.
        """
        logger.debug(f"Generating .qth file content for site '{name}'.")

        try:
            # Create the .qth file content
            contents = (
                f"{name}\n"
                f"{latitude:.6f}\n"
                f"{abs(longitude) if longitude < 0 else 360 - longitude:.6f}\n"  # SPLAT! expects west longitude as a positive number.
                f"{elevation:.2f}\n"
            )
            logger.debug(f"Generated .qth file contents:\n{contents}")
            return contents.encode('utf-8')  # Return as bytes
        except Exception as e:
            logger.error(f"Error generating .qth file content: {e}")
            raise ValueError(f"Failed to generate .qth content: {e}")

    @staticmethod
    def _create_splat_lrp(
            ground_dielectric: float,
            ground_conductivity: float,
            atmosphere_bending: float,
            frequency_mhz: float,
            radio_climate: Literal[
                "equatorial",
                "continental_subtropical",
                "maritime_subtropical",
                "desert",
                "continental_temperate",
                "maritime_temperate_land",
                "maritime_temperate_sea",
            ],
            polarization: Literal["horizontal", "vertical"],
            situation_fraction: float,
            time_fraction: float,
            tx_power: float,
            tx_gain: float,
            system_loss: float,

    ) -> bytes:
        """
        Generate the contents of a SPLAT! .lrp file describing environment and propagation parameters.

        Args:
            ground_dielectric (float): Earth's dielectric constant.
            ground_conductivity (float): Earth's conductivity (Siemens per meter).
            atmosphere_bending (float): Atmospheric bending constant.
            frequency_mhz (float): Frequency in MHz.
            radio_climate (str): Radio climate type.
            polarization (str): Antenna polarization.
            situation_fraction (float): Fraction of situations (percentage, 0-100).
            time_fraction (float): Fraction of time (percentage, 0-100).
            tx_power (float): Transmitter power in dBm.
            tx_gain (float): Transmitter antenna gain in dB.
            system_loss (float): System losses in dB (e.g., cable loss).

        Returns:
            bytes: The content of the .lrp file formatted for SPLAT!.
        """
        logger.debug("Generating .lrp file content.")

        # Mapping for radio climate and polarization to SPLAT! enumerations
        climate_map = {
            "equatorial": 1,
            "continental_subtropical": 2,
            "maritime_subtropical": 3,
            "desert": 4,
            "continental_temperate": 5,
            "maritime_temperate_land": 6,
            "maritime_temperate_sea": 7,
        }
        polarization_map = {"horizontal": 0, "vertical": 1}

        # Calculate ERP in Watts
        erp_watts = 10 ** ((tx_power + tx_gain - system_loss - 30) / 10)
        logger.debug(
            f"Calculated ERP in Watts: {erp_watts:.2f} "
            f"(tx_power={tx_power}, tx_gain={tx_gain}, system_loss={system_loss})"
        )

        # Generate the content, maintaining the SPLAT! format
        try:
            contents = (
                f"{ground_dielectric:.3f}  ; Earth Dielectric Constant\n"
                f"{ground_conductivity:.6f}  ; Earth Conductivity\n"
                f"{atmosphere_bending:.3f}  ; Atmospheric Bending Constant\n"
                f"{frequency_mhz:.3f}  ; Frequency in MHz\n"
                f"{climate_map[radio_climate]}  ; Radio Climate\n"
                f"{polarization_map[polarization]}  ; Polarization\n"
                f"{situation_fraction / 100.0:.2f} ; Fraction of situations\n"
                f"{time_fraction / 100.0:.2f}  ; Fraction of time\n"
                f"{erp_watts:.2f}  ; ERP in Watts\n"
            )
            logger.debug(f"Generated .lrp file contents:\n{contents}")
            return contents.encode('utf-8')  # Return as bytes
        except Exception as e:
            logger.error(f"Error generating .lrp file content: {e}")
            raise

    @staticmethod
    def _create_splat_dcf() -> bytes:
        """
        Generate a SPLAT! .dcf file with a linear grayscale ramp.

        Uses a fixed dBm range (-130 to -30) with 32 grayscale levels so that
        pixel values after convert("L") are proportional to dBm. Colormap is
        applied client-side.

        Returns:
            bytes: The content of the .dcf file formatted for SPLAT!.
        """
        min_dbm, max_dbm = -130, -30
        logger.debug("Generating grayscale .dcf file content.")

        try:
            cmap_values = np.linspace(max_dbm, min_dbm, 32)  # SPLAT! supports up to 32 levels
            # Linear grayscale ramp: strongest signal → brightest (247), weakest → darkest (0)
            gray_levels = np.linspace(247, 0, 32).astype(int)

            contents = "; SPLAT! Grayscale DCF (colormap applied client-side)\n;\n"
            contents += "; Format: dBm: red, green, blue\n;\n"
            for value, gray in zip(cmap_values, gray_levels):
                contents += f"{int(value):+4d}: {gray:3d}, {gray:3d}, {gray:3d}\n"

            logger.debug(f"Generated .dcf file contents:\n{contents}")
            return contents.encode("utf-8")

        except Exception as e:
            logger.error(f"Error generating .dcf file content: {e}")
            raise ValueError(f"Failed to generate .dcf content: {e}")

    @staticmethod
    def create_splat_colorbar(
        colormap_name: str,
        min_dbm: float,
        max_dbm: float,
    ) -> list:
        """Generate a list of RGB color values corresponding to the color map, min and max RSSI values in dBm."""
        cmap = plt.get_cmap(colormap_name, 256)  # colormap with 256 levels
        cmap_norm = plt.Normalize(vmin=min_dbm, vmax=max_dbm)  # Normalize based on dBm range
        cmap_values = np.linspace(min_dbm, max_dbm, 255)

        # Map data values to RGB for visible colors
        rgb_colors = (cmap(cmap_norm(cmap_values))[:, :3] * 255).astype(int)
        return rgb_colors


    @staticmethod
    def _create_splat_geotiff(
            ppm_bytes: bytes,
            kml_bytes: bytes,
            null_value: int = 255  # Define the null value for transparency
    ) -> bytes:
        """
        Generate a grayscale GeoTIFF from SPLAT! PPM and KML data.

        Pixel values 0-254 represent signal strength (proportional to dBm).
        Value 255 is noData (transparent). Colormap is applied client-side.

        Args:
            ppm_bytes (bytes): Binary content of the SPLAT-generated PPM file.
            kml_bytes (bytes): Binary content of the KML file containing geospatial bounds.
            null_value (int): Pixel value in the PPM that represents null areas. Defaults to 255.

        Returns:
            bytes: The binary content of the resulting GeoTIFF file.

        Raises:
            RuntimeError: If the conversion process fails.
        """
        logger.info("Starting grayscale GeoTIFF generation from SPLAT! PPM and KML data.")

        try:
            # Parse KML and extract bounding box
            logger.debug("Parsing KML content.")
            tree = ET.ElementTree(ET.fromstring(kml_bytes))
            namespace = {"kml": "http://earth.google.com/kml/2.1"}
            box = tree.find(".//kml:LatLonBox", namespace)

            north = float(box.find("kml:north", namespace).text)
            south = float(box.find("kml:south", namespace).text)
            east = float(box.find("kml:east", namespace).text)
            west = float(box.find("kml:west", namespace).text)

            logger.debug(
                f"Extracted bounding box: north={north}, south={south}, east={east}, west={west}"
            )

            # Read PPM content
            logger.debug("Reading PPM content.")
            with Image.open(io.BytesIO(ppm_bytes)) as img:
                img_array = np.array(
                    img.convert("L")
                )  # Convert to single-channel grayscale
                img_array = np.clip(img_array, 0, 255).astype("uint8")

            logger.debug(f"PPM image dimensions: {img_array.shape}")

            # Mask null values
            img_array = np.where(img_array == null_value, 255, img_array)
            no_data_value = null_value

            # Create GeoTIFF using Rasterio
            height, width = img_array.shape
            transform = from_bounds(west, south, east, north, width, height)
            logger.debug(f"GeoTIFF transform matrix: {transform}")

            # Write grayscale GeoTIFF to memory (no palette — colormap applied client-side)
            with io.BytesIO() as buffer:
                with rasterio.open(
                        buffer,
                        "w",
                        driver="GTiff",
                        height=height,
                        width=width,
                        count=1,  # Single-band data
                        dtype="uint8",
                        crs="EPSG:4326",
                        transform=transform,
                        photometric="minisblack",
                        compress="lzw",
                        nodata=no_data_value,
                ) as dst:
                    dst.write(img_array, 1)

                buffer.seek(0)
                geotiff_bytes = buffer.read()

            logger.info("Grayscale GeoTIFF generation successful.")
            return geotiff_bytes

        except Exception as e:
            logger.error(f"Error during GeoTIFF generation: {e}")
            raise RuntimeError(f"Error during GeoTIFF generation: {e}")

    def _download_terrain_tile(self, tile_name: str) -> bytes:
        """
        Downloads a terrain tile from the S3 bucket if not found in the local cache.

        This method checks if the requested tile is available in the cache..
        If the tile is not cached, it downloads the tile from the specified S3 bucket,
        stores it in the cache, and returns the tile data.

        Args:
            tile_name (str): The name of the terrain tile to be downloaded.

        Returns:
            bytes: The binary content of the terrain tile.

        Raises:
            Exception: If the tile cannot be downloaded from S3.
        """
        # Track popularity for the prefetch worker (best-effort, fire-and-forget).
        # Popularity ranking is per-source so prefetch warms the active source only.
        access_zset = f"dem:{self.dem_source}:access"
        if self._redis_tile_cache is not None:
            try:
                self._redis_tile_cache.zincrby(access_zset, 1, tile_name)
            except Exception:
                pass

        disk_key = self._disk_key(tile_name)
        if disk_key in self.tile_cache:
            logger.info(f"Cache hit (disk): {disk_key}")
            inc(srtm_cache_events_total, tier="disk", event="hit")
            return self.tile_cache[disk_key]

        redis_key = self.tile_redis_key(tile_name)
        if self._redis_tile_cache is not None:
            try:
                cached = self._redis_tile_cache.get(redis_key)
                if cached:
                    logger.info(f"Cache hit (redis): {disk_key}")
                    inc(srtm_cache_events_total, tier="redis", event="hit")
                    self.tile_cache[disk_key] = cached
                    return cached
            except Exception as e:
                logger.debug(f"Redis HGT cache read failed for {disk_key}: {e}")

        inc(srtm_cache_events_total, tier="s3", event="miss")

        if self.dem_source == "copernicus":
            tile_data = self._download_copernicus_tile(tile_name)
        elif self.dem_source == "fabdem":
            tile_data = self._download_fabdem_tile(tile_name)
        else:
            tile_data = self._download_srtm_tile(tile_name)

        # Spatial clutter (Phase C): fold canopy heights into the .hgt before
        # caching so the SDF that gets generated downstream sees a synthetic
        # DSM and SPLAT! treats vegetation as terrain.
        if self.clutter_source is not None:
            tile_data = self._apply_clutter(tile_data, tile_name)

        self._cache_tile(tile_name, redis_key, tile_data)
        return tile_data

    def _apply_clutter(self, tile_data: bytes, tile_name: str) -> bytes:
        """Add canopy height (× penetration factor) on top of a DTM tile.

        The DTM is delivered as a .hgt.gz buffer (3601×3601 int16 big-endian).
        We decode it, sum the canopy raster, clip to int16 range, and re-encode.
        If no canopy tile exists for this 1°×1° cell, we return the DTM untouched.
        """
        canopy = self.clutter_source.get_effective_height_grid(tile_name)
        if canopy is None:
            return tile_data
        raw = gzip.decompress(tile_data)
        dtm = np.frombuffer(raw, dtype=">i2").reshape(3601, 3601).astype("float32")
        # Preserve void cells (-32768) — adding canopy to a void is meaningless
        # and would corrupt the sentinel.
        void_mask = dtm <= -1000
        synthetic = np.where(void_mask, dtm, dtm + canopy)
        # Clip to int16 range. Real terrain + canopy will never approach the
        # bounds, but defend against malformed canopy data.
        synthetic = np.clip(synthetic, -32768, 32767).astype(">i2")
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(synthetic.tobytes())
        logger.info(
            f"Applied clutter ({self.clutter_source.name}, "
            f"factor={self.clutter_source.penetration_factor}) to {tile_name}"
        )
        return buf.getvalue()

    def _download_srtm_tile(self, tile_name: str) -> bytes:
        """Fetch a raw SRTM .hgt.gz tile from the configured S3 bucket."""
        tile_dir_prefix = tile_name[:3]
        s3_key = f"{self.bucket_prefix}/{tile_dir_prefix}/{tile_name}" if self.bucket_prefix else f"{tile_dir_prefix}/{tile_name}"
        logger.info(f"Downloading {tile_name} from {self.bucket_name}/{s3_key}...")
        try:
            obj = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            return obj['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"Tile {tile_name} not found in S3 bucket, trying to download V1 SRTM data instead: {e}")
                s3_key = f"skadi/{tile_dir_prefix}/{tile_name}"
                obj = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                return obj['Body'].read()
            logger.error(f"Failed to download {tile_name} from S3 due to ClientError: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to download {tile_name} from S3: {e}")
            raise

    def _download_copernicus_tile(self, tile_name: str) -> bytes:
        """Fetch a Copernicus GLO-30 COG and transcode it to SRTM-style .hgt.gz bytes.

        Copernicus tiles are GeoTIFFs in the public S3 bucket `copernicus-dem-30m`.
        The downstream pipeline expects raw .hgt.gz (16-bit big-endian, 3601×3601
        for 1-arcsec); we resample/encode here so srtm2sdf doesn't need to know
        about COGs.

        Args:
            tile_name: SRTM-style filename, e.g. ``N35W120.hgt.gz`` (used as cache key).

        Returns:
            bytes: gzipped raw HGT, drop-in for the SRTM path.
        """
        cop_key = self._copernicus_s3_key(tile_name)
        logger.info(f"Downloading Copernicus tile {tile_name} from {self.bucket_name}/{cop_key}...")
        try:
            obj = self.s3.get_object(Bucket=self.bucket_name, Key=cop_key)
            cog_bytes = obj["Body"].read()
        except ClientError as e:
            # Copernicus, like SRTM, has no tiles over open ocean. Surface a clear error.
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.warning(f"Copernicus tile not found at {cop_key} (likely ocean / no land coverage)")
            raise

        return self._cog_to_hgt_gz(cog_bytes)

    def _download_fabdem_tile(self, tile_name: str) -> bytes:
        """Fetch a FABDEM tile from the configured (operator-hosted) S3 bucket.

        FABDEM is CC BY-NC-SA, no public AWS Open Data mirror. If the tile is
        missing and `FABDEM_FALLBACK_SOURCE` is set, we transparently fall back
        to that DEM (typically Copernicus) so coastal / partially-covered areas
        keep working. The fallback is logged so operators can spot patchy
        coverage.

        Args:
            tile_name: SRTM-style filename used as cache key.

        Returns:
            bytes: gzipped raw HGT (drop-in for the SRTM path).
        """
        if not self.bucket_name:
            raise RuntimeError(
                "FABDEM is selected but FABDEM_BUCKET is not configured. "
                "Set FABDEM_BUCKET (and optionally FABDEM_PREFIX) to your "
                "operator-hosted S3 mirror."
            )

        cop_key = self._fabdem_s3_key(tile_name)
        full_key = f"{self.bucket_prefix.rstrip('/')}/{cop_key}" if self.bucket_prefix else cop_key
        logger.info(f"Downloading FABDEM tile {tile_name} from {self.bucket_name}/{full_key}...")
        try:
            obj = self.s3.get_object(Bucket=self.bucket_name, Key=full_key)
            cog_bytes = obj["Body"].read()
            return self._cog_to_hgt_gz(cog_bytes)
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchKey":
                raise
            if not FABDEM_FALLBACK_SOURCE:
                logger.warning(f"FABDEM tile {tile_name} missing and no fallback configured")
                raise
            logger.info(
                f"FABDEM tile {tile_name} missing; falling back to "
                f"{FABDEM_FALLBACK_SOURCE} for this tile only"
            )
            return self._download_with_alternate_source(tile_name, FABDEM_FALLBACK_SOURCE)

    def _download_with_alternate_source(self, tile_name: str, alt_source: str) -> bytes:
        """One-shot download using a different DEM source (used by the FABDEM fallback).

        Does NOT touch caches under the alternate source's namespace — the
        result is stored under the *current* source's key by `_cache_tile`,
        which is what the caller wants (so a future request for the same tile
        with FABDEM active still hits cache).
        """
        if alt_source not in DEM_SOURCES:
            raise ValueError(f"Unknown fallback source: {alt_source}")
        # Temporarily override bucket/prefix to the alternate source's defaults.
        original_bucket = self.bucket_name
        original_prefix = self.bucket_prefix
        original_source = self.dem_source
        try:
            alt_defaults = DEM_SOURCES[alt_source]
            self.bucket_name = alt_defaults["bucket"]
            self.bucket_prefix = alt_defaults["prefix"]
            self.dem_source = alt_source
            if alt_source == "copernicus":
                return self._download_copernicus_tile(tile_name)
            elif alt_source == "srtm":
                return self._download_srtm_tile(tile_name)
            elif alt_source == "fabdem":
                return self._download_fabdem_tile(tile_name)
            raise ValueError(f"Unsupported fallback source: {alt_source}")
        finally:
            self.bucket_name = original_bucket
            self.bucket_prefix = original_prefix
            self.dem_source = original_source

    @staticmethod
    def _fabdem_s3_key(tile_name: str) -> str:
        """Map an SRTM-style filename to the configured FABDEM filename.

        Example with default template: ``N35W120.hgt.gz`` → ``N35W120_FABDEM_V1-2.tif``.
        """
        ns = tile_name[0]
        lat = int(tile_name[1:3])
        ew = tile_name[3]
        lon = int(tile_name[4:7])
        return FABDEM_FILENAME_TEMPLATE.format(ns=ns, ew=ew, lat=lat, lon=lon)

    @staticmethod
    def _copernicus_s3_key(tile_name: str) -> str:
        """Map an SRTM-style filename to a Copernicus GLO-30 S3 key.

        Example: ``N35W120.hgt.gz`` →
        ``Copernicus_DSM_COG_10_N35_00_W120_00_DEM/Copernicus_DSM_COG_10_N35_00_W120_00_DEM.tif``
        """
        ns = tile_name[0]
        lat = int(tile_name[1:3])
        ew = tile_name[3]
        lon = int(tile_name[4:7])
        prefix = f"Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM"
        return f"{prefix}/{prefix}.tif"

    @staticmethod
    def _cog_to_hgt_gz(cog_bytes: bytes) -> bytes:
        """Resample a 1°×1° DEM COG to a 3601×3601 int16 big-endian .hgt.gz buffer.

        Copernicus GLO-30 tiles vary in column count by latitude (cosine
        compression at high latitudes); we resample everything back to a regular
        3601×3601 grid so GDAL's SRTMHGT driver can parse the result. NoData and
        non-finite values are encoded as -32768, matching the SRTM convention.
        """
        with rasterio.MemoryFile(cog_bytes) as memfile:
            with memfile.open() as src:
                data = src.read(
                    1,
                    out_shape=(3601, 3601),
                    resampling=Resampling.bilinear,
                ).astype("float32")
                src_nodata = src.nodata

        if src_nodata is not None:
            data = np.where(data == src_nodata, -32768.0, data)
        # SRTM convention: anything below -1000 m is treated as void.
        data = np.where(np.isfinite(data) & (data > -1000), data, -32768.0)
        arr = data.astype(">i2")  # int16 big-endian — exactly what srtm2sdf expects
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(arr.tobytes())
        return buf.getvalue()

    def _cache_tile(self, tile_name: str, redis_key: str, tile_data: bytes) -> None:
        """Persist a downloaded tile to both diskcache and Redis (best-effort)."""
        self.tile_cache[self._disk_key(tile_name)] = tile_data
        if self._redis_tile_cache is not None and SRTM_REDIS_TTL > 0:
            try:
                self._redis_tile_cache.setex(redis_key, SRTM_REDIS_TTL, tile_data)
            except Exception as e:
                logger.debug(f"Redis HGT cache write failed for {tile_name}: {e}")

    @staticmethod
    def _hgt_filename_to_sdf_filename(hgt_filename: str, high_resolution: bool = False) -> str:
            """ helper method to get the expected SPLAT! .sdf filename from the .hgt.gz terrain tile."""
            lat = int(hgt_filename[1:3]) * (1 if hgt_filename[0] == 'N' else -1)
            min_lon = int(hgt_filename[4:7]) - (-1 if hgt_filename[3] == 'E' else 1) # fix off-by-one error in eastern hemisphere
            min_lon = 360 - min_lon if hgt_filename[3] == 'E' else min_lon
            max_lon = 0 if min_lon == 359 else min_lon + 1
            return f"{lat}:{lat + 1}:{min_lon}:{max_lon}{'-hd.sdf' if high_resolution else '.sdf'}"

    def _convert_hgt_to_sdf(self, tile: bytes, tile_name: str, high_resolution: bool = False) -> bytes:
        """
        Converts a .hgt.gz terrain tile (provided as bytes) to a SPLAT! .sdf or -hd.sdf file.

        This method checks if the converted .sdf or -hd.sdf file corresponding to the tile_name
        exists in the cache. If not, the method decompresses the tile, places it in a temporary
        directory, performs the conversion using the SPLAT! utility (srtm2sdf or srtm2sdf-hd),
        and caches the resulting .sdf file.

        Args:
            tile (bytes): The binary content of the .hgt.gz terrain tile.
            tile_name (str): The name of the terrain tile (e.g., N35W120.hgt.gz).
            high_resolution (bool): Whether to generate a high-resolution -hd.sdf file. Defaults to False.

        Returns:
            bytes: The binary content of the converted .sdf or -hd.sdf file.

        Raises:
            RuntimeError: If the conversion fails.
        """

        sdf_filename = Splat._hgt_filename_to_sdf_filename(tile_name, high_resolution)
        sdf_disk_key = self._disk_key(sdf_filename)

        # Check cache for converted file
        if sdf_disk_key in self.tile_cache:
            logger.info(f"Cache hit (disk): {sdf_disk_key}")
            return self.tile_cache[sdf_disk_key]

        sdf_redis_key = self._sdf_redis_key(sdf_filename)
        if self._redis_tile_cache is not None:
            try:
                cached_sdf = self._redis_tile_cache.get(sdf_redis_key)
                if cached_sdf:
                    logger.info(f"Cache hit (redis): {sdf_disk_key}")
                    self.tile_cache[sdf_disk_key] = cached_sdf
                    return cached_sdf
            except Exception as e:
                logger.debug(f"Redis SDF cache read failed for {sdf_disk_key}: {e}")

        # Create temporary working directory
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                # Decompress the tile into the temporary directory
                hgt_path = os.path.join(tmpdir, tile_name.replace(".gz", ""))
                logger.info(f"Decompressing {tile_name} into {hgt_path}.")
                with gzip.GzipFile(fileobj=io.BytesIO(tile)) as gz_file:
                    with open(hgt_path, "wb") as hgt_file:
                        hgt_file.write(gz_file.read())

                # Downsample to 3-arcsecond resolution if not in high-resolution mode
                if not high_resolution:
                    try:
                        logger.info(f"Downsampling {hgt_path} to 3-arcsecond resolution.")
                        with rasterio.open(hgt_path) as src:
                            # Apply a scaling factor to transform for 3-arcsecond resolution
                            scale_factor = 3  # 3-arcsecond is 3 times coarser than 1-arcsecond
                            transform = src.transform * Affine.scale(scale_factor, scale_factor)

                            # Resample data to 3-arcsecond resolution
                            data = src.read(
                                # 3-arcsecond SRTM tiles always have dimensions of 1201x1201 pixels.
                                out_shape=(
                                    src.count,  # Number of bands
                                    1201,   # Downsampled height
                                    1201,   # Downsampled width
                                ),
                                resampling=Resampling.average,
                            )

                            # Update metadata for the new dataset
                            meta = src.meta.copy()
                            meta.update(
                                {
                                    "transform": transform,
                                    "width": 1201,
                                    "height": 1201,
                                }
                            )

                        # Overwrite the temporary file with downsampled data
                        with rasterio.open(hgt_path, "w", **meta) as dst:
                            dst.write(data)

                        logger.info(f"Successfully downsampled {hgt_path}.")
                    except Exception as e:
                        logger.error(f"Failed to downsample {hgt_path}: {e}")
                        raise RuntimeError(f"Downsampling error for {hgt_path}: {e}")

                # Call srtm2sdf or srtm2sdf-hd in the temporary directory
                cmd = self.srtm2sdf_hd_binary if high_resolution else self.srtm2sdf_binary
                logger.info(f"Converting {hgt_path} to {sdf_filename} using {cmd}.")
                result = subprocess.run(
                    [cmd, os.path.basename(tile_name.replace(".gz", ""))],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=True,
                )

                logger.debug(f"srtm2sdf output:\n{result.stderr}")
                sdf_path = os.path.join(tmpdir, sdf_filename)

                # Ensure the .sdf file was created
                if not os.path.exists(sdf_path):
                    logger.error(f"Expected .sdf file not found: {sdf_path}")
                    raise RuntimeError(f"Failed to generate .sdf file: {sdf_path}")

                # Read and cache the .sdf file
                with open(sdf_path, "rb") as sdf_file:
                    sdf_data = sdf_file.read()
                self._cache_tile(sdf_filename, sdf_redis_key, sdf_data)

                logger.info(f"Successfully converted and cached {sdf_filename}.")
                return sdf_data

            except subprocess.CalledProcessError as e:
                logger.error(f"Subprocess error during conversion of {tile_name}: {e}")
                logger.error(f"stderr: {e.stderr}")
                raise RuntimeError(f"Subprocess error during conversion of {tile_name}: {e}")

            except Exception as e:
                logger.error(f"Error during conversion of {tile_name} to {sdf_filename}: {e}")
                raise RuntimeError(f"Conversion error for {tile_name}: {e}")



if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG)
    try:
        splat_service = Splat(
            splat_path="",  # Replace with the actual SPLAT! binary path
        )

        # Create a test coverage prediction request
        test_coverage_request = CoveragePredictionRequest(
            lat=51.4408448,
            lon=-0.8994816,
            tx_height=1.0,
            ground_dielectric=15.0,
            ground_conductivity=0.005,
            atmosphere_bending=301.0,
            frequency_mhz=868.0,
            radio_climate="continental_temperate",
            polarization="vertical",
            situation_fraction=95.0,
            time_fraction=95.0,
            tx_power=30.0,
            tx_gain=1.0,
            system_loss=2.0,
            rx_height=1.0,
            radius=50000.0,
            colormap="CMRmap",
            min_dbm=-130.0,
            max_dbm=-80.0,
            signal_threshold=-130.0,
            high_resolution=False,
        )

        # Execute coverage prediction
        logger.info("Starting SPLAT! coverage prediction...")
        result = splat_service.coverage_prediction(test_coverage_request)

        # Save GeoTIFF output for inspection
        output_path = "splat_output.tif"
        with open(output_path, "wb") as output_file:
            output_file.write(result)
        logger.info(f"GeoTIFF saved to: {output_path}")

    except Exception as e:
        logger.error(f"Error during SPLAT! test: {e}")
        raise
