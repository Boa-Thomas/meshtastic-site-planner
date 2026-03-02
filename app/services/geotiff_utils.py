"""Shared GeoTIFF utilities for propagation engines."""

import io
import logging
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image

logger = logging.getLogger(__name__)


def ppm_kml_to_geotiff(
    ppm_bytes: bytes,
    kml_bytes: bytes,
    null_value: int = 255,
) -> bytes:
    """
    Generate a grayscale GeoTIFF from PPM and KML data.

    Pixel values 0-254 represent signal strength (proportional to dBm).
    Value 255 is noData (transparent). Colormap is applied client-side.

    Both SPLAT! and Signal Server produce PPM+KML output in the same format,
    so this function is shared between engines.

    Args:
        ppm_bytes: Binary content of the PPM file.
        kml_bytes: Binary content of the KML file containing geospatial bounds.
        null_value: Pixel value that represents null areas. Defaults to 255.

    Returns:
        The binary content of the resulting GeoTIFF file.

    Raises:
        RuntimeError: If the conversion process fails.
    """
    logger.info("Starting grayscale GeoTIFF generation from PPM and KML data.")

    try:
        # Parse KML and extract bounding box
        logger.debug("Parsing KML content.")
        tree = ET.ElementTree(ET.fromstring(kml_bytes))
        # Try both KML namespace versions
        box = None
        namespace = None
        for ns_uri in ("http://earth.google.com/kml/2.1", "http://www.opengis.net/kml/2.2"):
            namespace = {"kml": ns_uri}
            box = tree.find(".//kml:LatLonBox", namespace)
            if box is not None:
                break

        if box is None:
            raise RuntimeError("Could not find LatLonBox in KML data")

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
            img_array = np.array(img.convert("L"))
            img_array = np.clip(img_array, 0, 255).astype("uint8")

        logger.debug(f"PPM image dimensions: {img_array.shape}")

        # Mask null values
        img_array = np.where(img_array == null_value, 255, img_array)
        no_data_value = null_value

        # Create GeoTIFF using Rasterio
        height, width = img_array.shape
        transform = from_bounds(west, south, east, north, width, height)
        logger.debug(f"GeoTIFF transform matrix: {transform}")

        with io.BytesIO() as buffer:
            with rasterio.open(
                buffer,
                "w",
                driver="GTiff",
                height=height,
                width=width,
                count=1,
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
