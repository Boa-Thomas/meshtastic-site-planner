"""SQLAlchemy ORM model for the calibration_measurements table.

Stores ground-truth RSSI observations from the live Meshtastic network so the
penetration factor (and, eventually, other propagation knobs) can be calibrated
against real field data instead of guessed defaults.

Each row represents a single TX→RX measurement at a specific point in time. We
keep the snapshot of the RF parameters used at the time of measurement so a
later calibration run can reproduce the simulation conditions exactly.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from app.database import Base


class CalibrationMeasurement(Base):
    __tablename__ = "calibration_measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Geometry & time
    tx_lat = Column(Float, nullable=False)
    tx_lon = Column(Float, nullable=False)
    rx_lat = Column(Float, nullable=False)
    rx_lon = Column(Float, nullable=False)
    measured_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Measurement
    rssi_dbm = Column(Float, nullable=False)
    snr_db = Column(Float, nullable=True)

    # RF snapshot (denormalised on purpose — calibration data is append-only and
    # node configurations drift over time; we want each measurement to be
    # reproducible without joining a node table).
    frequency_mhz = Column(Float, nullable=False)
    tx_power_dbm = Column(Float, nullable=False)
    tx_gain_dbi = Column(Float, nullable=False)
    tx_height_m = Column(Float, nullable=False)
    rx_gain_dbi = Column(Float, nullable=False)
    rx_height_m = Column(Float, nullable=False)
    rx_loss_db = Column(Float, nullable=False, default=0.0)

    # Pipeline context — which terrain/clutter combination was active when the
    # node *should have* been heard. Lets `calibrate_clutter.py` group
    # measurements by configuration and avoid mixing apples and oranges.
    dem_source = Column(String(32), nullable=True)
    clutter_source = Column(String(32), nullable=True)
    clutter_penetration_factor = Column(Float, nullable=True)

    # Provenance
    source = Column(String(64), nullable=False, default="manual")  # 'manual', 'meshtastic-mqtt', etc.
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "txLat": self.tx_lat,
            "txLon": self.tx_lon,
            "rxLat": self.rx_lat,
            "rxLon": self.rx_lon,
            "measuredAt": self.measured_at.isoformat() if self.measured_at else None,
            "rssiDbm": self.rssi_dbm,
            "snrDb": self.snr_db,
            "frequencyMhz": self.frequency_mhz,
            "txPowerDbm": self.tx_power_dbm,
            "txGainDbi": self.tx_gain_dbi,
            "txHeightM": self.tx_height_m,
            "rxGainDbi": self.rx_gain_dbi,
            "rxHeightM": self.rx_height_m,
            "rxLossDb": self.rx_loss_db,
            "demSource": self.dem_source,
            "clutterSource": self.clutter_source,
            "clutterPenetrationFactor": self.clutter_penetration_factor,
            "source": self.source,
            "notes": self.notes,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
