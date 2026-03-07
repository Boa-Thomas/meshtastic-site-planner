"""Signal Server propagation engine implementation."""

import logging
import os
import subprocess
import tempfile
from typing import Optional

from app.models.CoveragePredictionRequest import CoveragePredictionRequest
from app.services.engine import PropagationEngine
from app.services.geotiff_utils import ppm_kml_to_geotiff

logger = logging.getLogger(__name__)

# Signal Server propagation model codes
PROPAGATION_MODELS = {
    "itm": 1,
    "los": 2,
    "hata": 3,
    "cost231": 7,
    "fspl": 8,
    "itwom": 9,
    "ericsson": 10,
}


class SignalServerEngine(PropagationEngine):
    """
    Propagation engine using Signal Server / Signal Server HD.

    Signal Server is an RF coverage prediction tool that supports multiple
    propagation models (ITM, Hata, COST-231, etc.) and produces PPM+KML
    output compatible with the same GeoTIFF conversion used by SPLAT!.

    See: https://github.com/Cloud-RF/Signal-Server
    """

    def __init__(
        self,
        binary_path: str = "/usr/local/bin/signalserverHD",
        sdf_path: Optional[str] = None,
        default_model: str = "itm",
    ):
        self._binary_path = binary_path
        self._sdf_path = sdf_path or os.environ.get("SIGNAL_SERVER_SDF_PATH", "")
        self._default_model = default_model
        logger.info(f"Initialized SignalServerEngine (binary={binary_path}, model={default_model})")

    @property
    def name(self) -> str:
        return "signal_server"

    def is_available(self) -> bool:
        return os.path.isfile(self._binary_path) and os.access(self._binary_path, os.X_OK)

    def coverage_prediction(self, request: CoveragePredictionRequest, *, task_id: str | None = None) -> bytes:
        logger.info(f"Signal Server prediction: lat={request.lat}, lon={request.lon}, radius={request.radius}m")

        model_name = getattr(request, "propagation_model", None) or self._default_model
        model_code = PROPAGATION_MODELS.get(model_name, 1)

        # Calculate ERP in Watts
        erp_watts = 10 ** ((request.tx_power + request.tx_gain - request.system_loss - 30) / 10)

        # Polarization: 0=horizontal, 1=vertical
        pol_map = {"horizontal": 0, "vertical": 1}
        pol = pol_map.get(request.polarization, 1)

        # Radio climate mapping
        climate_map = {
            "equatorial": 1,
            "continental_subtropical": 2,
            "maritime_subtropical": 3,
            "desert": 4,
            "continental_temperate": 5,
            "maritime_temperate_land": 6,
            "maritime_temperate_sea": 7,
        }
        climate = climate_map.get(request.radio_climate, 5)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_base = os.path.join(tmpdir, "output")

            cmd = [
                self._binary_path,
                "-lat", str(request.lat),
                "-lon", str(request.lon),
                "-txh", str(request.tx_height),
                "-f", str(request.frequency_mhz),
                "-erp", str(erp_watts),
                "-rxh", str(request.rx_height),
                "-R", str(request.radius / 1000.0),  # km
                "-pm", str(model_code),
                "-cl", str(climate),
                "-pol", str(pol),
                "-gc", str(request.clutter_height),
                "-o", output_base,
                "-dbm",
                "-rt", str(request.signal_threshold),
                "-m",  # metric
                "-kml",
            ]

            # Add SDF path if available
            if self._sdf_path:
                cmd.extend(["-sdf", self._sdf_path])

            logger.debug(f"Signal Server command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=tmpdir,
                capture_output=True,
                text=True,
                check=False,
            )

            logger.debug(f"Signal Server stdout:\n{result.stdout}")
            logger.debug(f"Signal Server stderr:\n{result.stderr}")

            if result.returncode != 0:
                raise RuntimeError(
                    f"Signal Server failed with return code {result.returncode}\n"
                    f"Stdout: {result.stdout}\nStderr: {result.stderr}"
                )

            ppm_path = f"{output_base}.ppm"
            kml_path = f"{output_base}.kml"

            if not os.path.exists(ppm_path):
                raise RuntimeError(f"Signal Server did not produce PPM output: {ppm_path}")
            if not os.path.exists(kml_path):
                raise RuntimeError(f"Signal Server did not produce KML output: {kml_path}")

            with open(ppm_path, "rb") as f:
                ppm_data = f.read()
            with open(kml_path, "rb") as f:
                kml_data = f.read()

            return ppm_kml_to_geotiff(ppm_data, kml_data)
