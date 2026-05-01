from pydantic import BaseModel, Field
from typing import Optional, Literal
import hashlib
import json
import matplotlib.pyplot as plt

AVAILABLE_COLORMAPS = plt.colormaps()


class CoveragePredictionRequest(BaseModel):
    """
    Input payload for /coverage.
    """

    # Transmitter
    lat: float = Field(
        ge=-90, le=90, description="Transmitter latitude in degrees (-90 to 90)"
    )
    lon: float = Field(
        ge=-180, le=180, description="Transmitter longitude in degrees (-180 to 180)"
    )
    tx_height: float = Field(
        1, ge=1, description="Transmitter height above ground in meters (>= 1 m)"
    )
    tx_power: float = Field(gt=0, description="Transmitter power in dBm (>= 1 dBm)")
    tx_gain: float = Field(1, ge=0, description="Transmitter antenna gain in dB (>= 0)")
    frequency_mhz: float = Field(
        905.0, ge=20, le=30000, description="Operating frequency in MHz (20-30000 MHz)"
    )

    # Receiver
    rx_height: float = Field(
        1, ge=1, description="Receiver height above ground in meters (>= 1 m)"
    )
    rx_gain: float = Field(1, ge=0, description="Receiver antenna gain in dB (>= 0)")
    signal_threshold: float = Field(
        -100, le=0, description="Signal cutoff in dBm (<= 0)"
    )
    clutter_height: float = Field(
        0, ge=0, description="Ground clutter height in meters (>= 0)"
    )

    # Environmental
    ground_dielectric: Optional[float] = Field(
        15.0, ge=1, description="Ground dielectric constant (default: 15.0)"
    )
    ground_conductivity: Optional[float] = Field(
        0.005, ge=0, description="Ground conductivity in S/m (default: 0.005)"
    )
    atmosphere_bending: Optional[float] = Field(
        301.0,
        ge=0,
        description="Atmospheric bending constant in N-units (default: 301.0)",
    )

    # Model Settings
    radius: float = Field(
        1000.0, ge=1, description="Model maximum range in meters (>= 1 m)"
    )
    system_loss: Optional[float] = Field(
        0.0, ge=0, description="System loss in dB (default: 0.0)"
    )
    radio_climate: Literal[
        "equatorial",
        "continental_subtropical",
        "maritime_subtropical",
        "desert",
        "continental_temperate",
        "maritime_temperate_land",
        "maritime_temperate_sea",
    ] = Field(
        "continental_temperate",
        description="Radio climate, e.g., 'equatorial', 'continental_temperate' (default: 'continental_temperate')",
    )
    polarization: Literal["horizontal", "vertical"] = Field(
        "vertical",
        description="Signal polarization, 'horizontal' or 'vertical' (default: 'vertical')",
    )
    situation_fraction: Optional[float] = Field(
        50,
        gt=1,
        le=100,
        description="Percentage of locations within the modeled area where the signal prediction is expected to be valid (default 50).",
    )
    time_fraction: Optional[float] = Field(
        90,
        gt=1,
        le=100,
        description="Percentage of times where the signal prediction is expected to be valid (default 90).",
    )

    # Output Settings
    colormap: Literal[tuple(AVAILABLE_COLORMAPS)] = Field(
        "rainbow",
        description=f"Matplotlib colormap to use. Available options: {', '.join(AVAILABLE_COLORMAPS)}",
    )
    min_dbm: float = Field(
        -130.0,
        description="Minimum dBm value for the colormap (default: -130.0).",
    )
    max_dbm: float = Field(
        -30.0,
        description="Maximum dBm value for the colormap (default: -30.0).",
    )

    high_resolution: bool = Field(
        False,
        description="Use optional 1-arcsecond / 30 meter resolution  terrain tiles instead of the default 3-arcsecond / 90 meter (default: False).",
    )

    engine: Optional[str] = Field(
        None,
        description="Propagation engine to use ('splat' or 'signal_server'). Defaults to server config.",
    )

    propagation_model: Optional[str] = Field(
        None,
        description="Propagation model for Signal Server (e.g., 'itm', 'hata', 'cost231', 'itwom'). Ignored for SPLAT!.",
    )

    # Terrain / clutter overrides — let the caller pick a DEM source and a
    # spatial clutter dataset on a per-request basis. None means "use whatever
    # the server is configured for" (env vars). Only applied to the splat
    # engine; signal_server ignores them.
    dem_source: Optional[Literal["srtm", "copernicus", "fabdem"]] = Field(
        None,
        description="DEM source override. Defaults to the server's DEM_SOURCE env var.",
    )
    clutter_source: Optional[Literal["none", "lang2023", "mapbiomas", "custom"]] = Field(
        None,
        description="Spatial clutter source override. 'none' disables spatial clutter for this request.",
    )
    clutter_penetration_factor: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Override CLUTTER_PENETRATION_FACTOR for this request (0.0 = invisible, 1.0 = solid).",
    )

    def _rf_significant_params(self, lat: float, lon: float) -> dict:
        """Return the dict of RF-significant params using the supplied lat/lon."""
        return {
            "lat": lat,
            "lon": lon,
            "tx_height": round(self.tx_height, 2),
            "tx_power": round(self.tx_power, 2),
            "tx_gain": round(self.tx_gain, 2),
            "frequency_mhz": round(self.frequency_mhz, 3),
            "rx_height": round(self.rx_height, 2),
            "rx_gain": round(self.rx_gain, 2),
            "signal_threshold": round(self.signal_threshold, 1),
            "clutter_height": round(self.clutter_height, 2),
            "ground_dielectric": round(self.ground_dielectric, 3),
            "ground_conductivity": round(self.ground_conductivity, 6),
            "atmosphere_bending": round(self.atmosphere_bending, 3),
            "radius": round(self.radius, 0),
            "system_loss": round(self.system_loss, 2),
            "radio_climate": self.radio_climate,
            "polarization": self.polarization,
            "situation_fraction": round(self.situation_fraction, 1),
            "time_fraction": round(self.time_fraction, 1),
            "high_resolution": self.high_resolution,
            "engine": self.engine,
            "propagation_model": self.propagation_model,
            # Terrain identity is part of the RF-significant set: different DEM
            # / clutter combinations produce different coverage maps, so the
            # cache must distinguish them.
            "dem_source": self.dem_source,
            "clutter_source": self.clutter_source,
            "clutter_penetration_factor": (
                round(self.clutter_penetration_factor, 3)
                if self.clutter_penetration_factor is not None
                else None
            ),
        }

    def rf_param_hash(self) -> str:
        """SHA-256 hash of RF-significant parameters (excludes display-only params like colormap)."""
        significant = self._rf_significant_params(round(self.lat, 6), round(self.lon, 6))
        return hashlib.sha256(json.dumps(significant, sort_keys=True).encode()).hexdigest()[:16]

    def rf_neighborhood_hashes(self, grid_deg: float = 0.0005) -> list[str]:
        """
        Hashes for this request's grid cell plus the 8 neighbors.

        grid_deg = 0.0005 ≈ 55m. Two requests within `grid_deg` of each other
        (and identical RF params) will share at least one neighborhood hash.

        Returned in proximity order (center first), so callers can iterate and
        accept the first cache hit.
        """
        if grid_deg <= 0:
            return []
        gx = round(self.lon / grid_deg) * grid_deg
        gy = round(self.lat / grid_deg) * grid_deg
        deltas = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
                  (1, 1), (-1, 1), (1, -1), (-1, -1)]
        hashes = []
        for dx, dy in deltas:
            cx = round(gx + dx * grid_deg, 6)
            cy = round(gy + dy * grid_deg, 6)
            payload = self._rf_significant_params(cy, cx)
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
            hashes.append(digest)
        return hashes
