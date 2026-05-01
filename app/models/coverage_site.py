"""SQLAlchemy ORM model for the coverage_sites table."""

import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.database import Base


def _to_nested_params(raw: dict, task_id: str) -> dict:
    """Wrap the flat CoveragePredictionRequest shape into the nested
    SplatParams shape the frontend renders. Synthesizes a transmitter name
    from the task_id since the flat payload doesn't carry one."""
    if not isinstance(raw, dict) or "transmitter" in raw:
        return raw
    return {
        "transmitter": {
            "name": f"Site {task_id[:8]}",
            "tx_lat": raw.get("lat"),
            "tx_lon": raw.get("lon"),
            "tx_power": raw.get("tx_power"),
            "tx_gain": raw.get("tx_gain"),
            "frequency_mhz": raw.get("frequency_mhz"),
        },
        "receiver": {
            "rx_height": raw.get("rx_height"),
            "rx_gain": raw.get("rx_gain"),
            "signal_threshold": raw.get("signal_threshold"),
            "rx_loss": raw.get("system_loss"),
        },
        "environment": {
            "radio_climate": raw.get("radio_climate"),
            "polarization": raw.get("polarization"),
            "clutter_height": raw.get("clutter_height"),
            "ground_dielectric": raw.get("ground_dielectric"),
            "ground_conductivity": raw.get("ground_conductivity"),
            "atmosphere_bending": raw.get("atmosphere_bending"),
        },
        "simulation": {
            "situation_fraction": raw.get("situation_fraction"),
            "time_fraction": raw.get("time_fraction"),
            "radius": raw.get("radius"),
            "high_resolution": raw.get("high_resolution"),
        },
        "display": {
            "color_scale": raw.get("colormap"),
            "min_dbm": raw.get("min_dbm"),
            "max_dbm": raw.get("max_dbm"),
            "overlay_transparency": 50,
        },
        "tx_height": raw.get("tx_height"),
    }


class CoverageSite(Base):
    __tablename__ = "coverage_sites"

    task_id = Column(String(36), primary_key=True)
    params = Column(Text, nullable=False)  # Full SplatParams as JSON
    raster_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        try:
            raw = json.loads(self.params) if isinstance(self.params, str) else self.params
        except (json.JSONDecodeError, TypeError):
            raw = {}
        return {
            "taskId": self.task_id,
            "params": _to_nested_params(raw, self.task_id),
            "rasterPath": self.raster_path,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
