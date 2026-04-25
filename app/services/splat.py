import gzip
import logging
import math
import os
import io
import subprocess
import tempfile
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
from app.services.geotiff_utils import ppm_kml_to_geotiff
from app.redis_config import DB_SRTM_CACHE, get_redis_client


logger = logging.getLogger(__name__)

# Redis HGT tile cache shared across workers; survives diskcache LRU eviction.
# Set REDIS_SRTM_CACHE_TTL=0 to disable persistence-side caching.
SRTM_REDIS_TTL = int(os.environ.get("REDIS_SRTM_CACHE_TTL", str(7 * 24 * 3600)))
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("s3transfer").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class Splat(PropagationEngine):
    def __init__(
        self,
        splat_path: str,
        cache_dir: str = ".splat_tiles",
        cache_size_gb: float = 1.0,
        bucket_name: str = "elevation-tiles-prod",
        bucket_prefix:str = "v2/skadi"
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
            bucket_name (str): Name of the S3 bucket containing terrain tiles. Defaults to the AWS
                open data bucket `elevation-tiles-prod`.
            bucket_prefix (str): Folder in the S3 bucket containing the terrain tiles. Defaults to
                `v2/skadi`, which contains 1-arcsecond terrain data for most of the world.
        """

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

        self.s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
        self.bucket_name = bucket_name
        self.bucket_prefix = bucket_prefix

        logger.info(
            f"Initialized SPLAT! with terrain tile cache at '{cache_dir}' with a size limit of {cache_size_gb} GB."
        )

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

                # download and convert terrain tiles to SPLAT! sdf (parallel)
                max_workers = min(len(required_tiles), 8)
                completed_tiles = 0
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            self._download_and_convert_tile,
                            tile_name, sdf_name, sdf_hd_name,
                            request.high_resolution, tmpdir
                        ): tile_name
                        for tile_name, sdf_name, sdf_hd_name in required_tiles
                    }
                    for future in as_completed(futures):
                        future.result()  # Propagate exceptions
                        completed_tiles += 1
                        tile_progress = 0.05 + (completed_tiles / total_tiles) * 0.25
                        self._report_progress(task_id, "downloading_tiles", tile_progress,
                                              f"{completed_tiles}/{total_tiles} tiles")

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
                    "-gc",
                    str(request.clutter_height),
                    "-ngs",
                    "-N",
                    "-o",
                    "output.ppm",
                    "-dbm",
                    "-db",
                    str(request.signal_threshold),
                    "-kml",
                    "-olditm"
                ] # flag "olditm" uses the standard ITM model instead of ITWOM, which has produced unrealistic results.
                logger.debug(f"Executing SPLAT! command: {' '.join(splat_command)}")

                splat_result = subprocess.run(
                    splat_command,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False,
                )

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
        """Download a terrain tile, convert to SDF, and write to tmpdir."""
        tile_data = self._download_terrain_tile(tile_name)
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
        if tile_name in self.tile_cache:
            logger.info(f"Cache hit (disk): {tile_name}")
            return self.tile_cache[tile_name]

        redis_key = f"srtm:hgt:{tile_name}"
        if self._redis_tile_cache is not None:
            try:
                cached = self._redis_tile_cache.get(redis_key)
                if cached:
                    logger.info(f"Cache hit (redis): {tile_name}")
                    self.tile_cache[tile_name] = cached
                    return cached
            except Exception as e:
                logger.debug(f"Redis HGT cache read failed for {tile_name}: {e}")

        # Download the tile from S3 if not in cache
        tile_dir_prefix = tile_name[:3]
        s3_key = f"{self.bucket_prefix}/{tile_dir_prefix}/{tile_name}"
        logger.info(f"Downloading {tile_name} from {self.bucket_name}/{s3_key}...")
        try:
            obj = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
            tile_data = obj['Body'].read()
            self._cache_tile(tile_name, redis_key, tile_data)
            return tile_data
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info(f"Tile {tile_name} not found in S3 bucket, trying to download V1 SRTM data instead: {e}")
                s3_key = f"skadi/{tile_dir_prefix}/{tile_name}"
                obj = self.s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                tile_data = obj['Body'].read()
                self._cache_tile(tile_name, redis_key, tile_data)
                return tile_data
            else:
                logger.error(f"Failed to download {tile_name} from S3 due to ClientError: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to download {tile_name} from S3: {e}")
            raise

    def _cache_tile(self, tile_name: str, redis_key: str, tile_data: bytes) -> None:
        """Persist a downloaded tile to both diskcache and Redis (best-effort)."""
        self.tile_cache[tile_name] = tile_data
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

        # Check cache for converted file
        if sdf_filename in self.tile_cache:
            logger.info(f"Cache hit: {sdf_filename} found in the local cache.")
            return self.tile_cache[sdf_filename]

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
                self.tile_cache[sdf_filename] = sdf_data

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
