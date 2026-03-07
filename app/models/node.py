"""SQLAlchemy ORM model for the nodes table."""

import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, Text
from app.database import Base


class Node(Base):
    __tablename__ = "nodes"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    tx_power_w = Column(Float, nullable=False)
    tx_power_dbm = Column(Float, nullable=False)
    frequency_mhz = Column(Float, nullable=False)
    tx_gain_dbi = Column(Float, nullable=False)
    antenna_height = Column(Float, nullable=False)
    rx_sensitivity_dbm = Column(Float, nullable=False)
    rx_gain_dbi = Column(Float, nullable=False)
    rx_loss_db = Column(Float, nullable=False)
    installation_type = Column(String(20), nullable=False)
    antenna_orientation = Column(String(20), nullable=False)
    obstruction_level = Column(String(10), nullable=False)
    channel_preset_id = Column(String(30), nullable=False)
    hop_limit = Column(Integer, nullable=False)
    device_preset_id = Column(String(50), nullable=True)
    elevation_m = Column(Float, nullable=True)
    site_id = Column(String(36), nullable=True)
    directional_params = Column(Text, nullable=True)  # JSON
    window_cone = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Convert to camelCase dict matching the MeshNode TypeScript interface."""
        result = {
            "id": self.id,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "txPowerW": self.tx_power_w,
            "txPowerDbm": self.tx_power_dbm,
            "frequencyMhz": self.frequency_mhz,
            "txGainDbi": self.tx_gain_dbi,
            "antennaHeight": self.antenna_height,
            "rxSensitivityDbm": self.rx_sensitivity_dbm,
            "rxGainDbi": self.rx_gain_dbi,
            "rxLossDb": self.rx_loss_db,
            "installationType": self.installation_type,
            "antennaOrientation": self.antenna_orientation,
            "obstructionLevel": self.obstruction_level,
            "channelPresetId": self.channel_preset_id,
            "hopLimit": self.hop_limit,
        }
        if self.device_preset_id is not None:
            result["devicePresetId"] = self.device_preset_id
        if self.elevation_m is not None:
            result["elevationM"] = self.elevation_m
        if self.site_id is not None:
            result["siteId"] = self.site_id
        if self.directional_params:
            result["directionalParams"] = json.loads(self.directional_params)
        if self.window_cone:
            result["windowCone"] = json.loads(self.window_cone)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        """Create a Node from a camelCase dict (frontend JSON)."""
        node = cls(
            id=data.get("id"),
            name=data["name"],
            lat=data["lat"],
            lon=data["lon"],
            tx_power_w=data["txPowerW"],
            tx_power_dbm=data["txPowerDbm"],
            frequency_mhz=data["frequencyMhz"],
            tx_gain_dbi=data["txGainDbi"],
            antenna_height=data["antennaHeight"],
            rx_sensitivity_dbm=data["rxSensitivityDbm"],
            rx_gain_dbi=data["rxGainDbi"],
            rx_loss_db=data["rxLossDb"],
            installation_type=data["installationType"],
            antenna_orientation=data["antennaOrientation"],
            obstruction_level=data["obstructionLevel"],
            channel_preset_id=data["channelPresetId"],
            hop_limit=data["hopLimit"],
            device_preset_id=data.get("devicePresetId"),
            elevation_m=data.get("elevationM"),
            site_id=data.get("siteId"),
            directional_params=json.dumps(data["directionalParams"]) if data.get("directionalParams") else None,
            window_cone=json.dumps(data["windowCone"]) if data.get("windowCone") else None,
        )
        return node

    def update_from_dict(self, data: dict):
        """Update fields from a camelCase dict (partial update supported)."""
        field_map = {
            "name": "name",
            "lat": "lat",
            "lon": "lon",
            "txPowerW": "tx_power_w",
            "txPowerDbm": "tx_power_dbm",
            "frequencyMhz": "frequency_mhz",
            "txGainDbi": "tx_gain_dbi",
            "antennaHeight": "antenna_height",
            "rxSensitivityDbm": "rx_sensitivity_dbm",
            "rxGainDbi": "rx_gain_dbi",
            "rxLossDb": "rx_loss_db",
            "installationType": "installation_type",
            "antennaOrientation": "antenna_orientation",
            "obstructionLevel": "obstruction_level",
            "channelPresetId": "channel_preset_id",
            "hopLimit": "hop_limit",
            "devicePresetId": "device_preset_id",
            "elevationM": "elevation_m",
            "siteId": "site_id",
        }
        for camel, snake in field_map.items():
            if camel in data:
                setattr(self, snake, data[camel])
        if "directionalParams" in data:
            self.directional_params = json.dumps(data["directionalParams"]) if data["directionalParams"] else None
        if "windowCone" in data:
            self.window_cone = json.dumps(data["windowCone"]) if data["windowCone"] else None
        self.updated_at = datetime.now(timezone.utc)
