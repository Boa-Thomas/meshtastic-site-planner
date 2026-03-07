"""Pydantic schemas for API request/response validation."""

from typing import Optional
from pydantic import BaseModel, Field


class DirectionalParams(BaseModel):
    azimuth: float
    beamwidth: float


class WindowCone(BaseModel):
    start_deg: float = Field(alias="startDeg")
    end_deg: float = Field(alias="endDeg")

    model_config = {"populate_by_name": True}


class NodeCreate(BaseModel):
    """Schema for creating a node. All fields match the MeshNode TS interface."""
    id: Optional[str] = None
    name: str
    lat: float
    lon: float
    tx_power_w: float = Field(alias="txPowerW")
    tx_power_dbm: float = Field(alias="txPowerDbm")
    frequency_mhz: float = Field(alias="frequencyMhz")
    tx_gain_dbi: float = Field(alias="txGainDbi")
    antenna_height: float = Field(alias="antennaHeight")
    rx_sensitivity_dbm: float = Field(alias="rxSensitivityDbm")
    rx_gain_dbi: float = Field(alias="rxGainDbi")
    rx_loss_db: float = Field(alias="rxLossDb")
    installation_type: str = Field(alias="installationType")
    antenna_orientation: str = Field(alias="antennaOrientation")
    obstruction_level: str = Field(alias="obstructionLevel")
    channel_preset_id: str = Field(alias="channelPresetId")
    hop_limit: int = Field(alias="hopLimit")
    device_preset_id: Optional[str] = Field(default=None, alias="devicePresetId")
    elevation_m: Optional[float] = Field(default=None, alias="elevationM")
    site_id: Optional[str] = Field(default=None, alias="siteId")
    directional_params: Optional[DirectionalParams] = Field(default=None, alias="directionalParams")
    window_cone: Optional[WindowCone] = Field(default=None, alias="windowCone")

    model_config = {"populate_by_name": True}


class NodeUpdate(BaseModel):
    """Schema for updating a node. All fields optional for partial updates."""
    name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    tx_power_w: Optional[float] = Field(default=None, alias="txPowerW")
    tx_power_dbm: Optional[float] = Field(default=None, alias="txPowerDbm")
    frequency_mhz: Optional[float] = Field(default=None, alias="frequencyMhz")
    tx_gain_dbi: Optional[float] = Field(default=None, alias="txGainDbi")
    antenna_height: Optional[float] = Field(default=None, alias="antennaHeight")
    rx_sensitivity_dbm: Optional[float] = Field(default=None, alias="rxSensitivityDbm")
    rx_gain_dbi: Optional[float] = Field(default=None, alias="rxGainDbi")
    rx_loss_db: Optional[float] = Field(default=None, alias="rxLossDb")
    installation_type: Optional[str] = Field(default=None, alias="installationType")
    antenna_orientation: Optional[str] = Field(default=None, alias="antennaOrientation")
    obstruction_level: Optional[str] = Field(default=None, alias="obstructionLevel")
    channel_preset_id: Optional[str] = Field(default=None, alias="channelPresetId")
    hop_limit: Optional[int] = Field(default=None, alias="hopLimit")
    device_preset_id: Optional[str] = Field(default=None, alias="devicePresetId")
    elevation_m: Optional[float] = Field(default=None, alias="elevationM")
    site_id: Optional[str] = Field(default=None, alias="siteId")
    directional_params: Optional[DirectionalParams] = Field(default=None, alias="directionalParams")
    window_cone: Optional[WindowCone] = Field(default=None, alias="windowCone")

    model_config = {"populate_by_name": True}


class CoverageSiteResponse(BaseModel):
    task_id: str = Field(alias="taskId")
    params: str
    raster_path: str = Field(alias="rasterPath")
    created_at: Optional[str] = Field(default=None, alias="createdAt")

    model_config = {"populate_by_name": True}
