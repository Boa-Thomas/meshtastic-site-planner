"""Calibration endpoints — collect ground-truth RSSI measurements.

The penetration factor default of 0.6 is a placeholder. Calibrating it
requires a corpus of (TX, RX, RSSI_measured) tuples from the live network.
This router accepts and exposes those measurements so the offline solver
script (`utils/calibrate_clutter.py`) can fit a factor against real data.

The endpoint is intentionally permissive about RF context — operators can
backfill measurements without exact pipeline metadata. Calibration jobs
filter by what's available.
"""

from datetime import datetime
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.calibration_measurement import CalibrationMeasurement

router = APIRouter(prefix="/api/calibration", tags=["calibration"])


class MeasurementIn(BaseModel):
    tx_lat: float = Field(ge=-90, le=90)
    tx_lon: float = Field(ge=-180, le=180)
    rx_lat: float = Field(ge=-90, le=90)
    rx_lon: float = Field(ge=-180, le=180)
    rssi_dbm: float = Field(le=0, description="Measured RSSI at RX in dBm (≤ 0)")
    snr_db: Optional[float] = None
    frequency_mhz: float = Field(ge=20, le=30000)
    tx_power_dbm: float
    tx_gain_dbi: float = Field(ge=0)
    tx_height_m: float = Field(ge=0)
    rx_gain_dbi: float = Field(ge=0)
    rx_height_m: float = Field(ge=0)
    rx_loss_db: float = Field(0.0, ge=0)
    measured_at: Optional[datetime] = None
    dem_source: Optional[Literal["srtm", "copernicus", "fabdem"]] = None
    clutter_source: Optional[Literal["none", "lang2023", "mapbiomas", "custom"]] = None
    clutter_penetration_factor: Optional[float] = Field(None, ge=0.0, le=1.0)
    source: str = Field("manual", max_length=64)
    notes: Optional[str] = None


class MeasurementOut(MeasurementIn):
    id: int


@router.post("/measurements", status_code=201)
def create_measurement(payload: MeasurementIn, db: Session = Depends(get_db)) -> dict:
    measurement = CalibrationMeasurement(
        tx_lat=payload.tx_lat,
        tx_lon=payload.tx_lon,
        rx_lat=payload.rx_lat,
        rx_lon=payload.rx_lon,
        rssi_dbm=payload.rssi_dbm,
        snr_db=payload.snr_db,
        frequency_mhz=payload.frequency_mhz,
        tx_power_dbm=payload.tx_power_dbm,
        tx_gain_dbi=payload.tx_gain_dbi,
        tx_height_m=payload.tx_height_m,
        rx_gain_dbi=payload.rx_gain_dbi,
        rx_height_m=payload.rx_height_m,
        rx_loss_db=payload.rx_loss_db,
        measured_at=payload.measured_at or datetime.utcnow(),
        dem_source=payload.dem_source,
        clutter_source=payload.clutter_source,
        clutter_penetration_factor=payload.clutter_penetration_factor,
        source=payload.source,
        notes=payload.notes,
    )
    db.add(measurement)
    db.commit()
    db.refresh(measurement)
    return measurement.to_dict()


@router.get("/measurements")
def list_measurements(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    dem_source: Optional[str] = None,
    clutter_source: Optional[str] = None,
    source: Optional[str] = None,
) -> dict:
    query = db.query(CalibrationMeasurement)
    if dem_source:
        query = query.filter(CalibrationMeasurement.dem_source == dem_source)
    if clutter_source:
        query = query.filter(CalibrationMeasurement.clutter_source == clutter_source)
    if source:
        query = query.filter(CalibrationMeasurement.source == source)
    total = query.count()
    rows = (
        query.order_by(CalibrationMeasurement.measured_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [r.to_dict() for r in rows],
    }


@router.get("/measurements/{measurement_id}")
def get_measurement(measurement_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(CalibrationMeasurement, measurement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return row.to_dict()


@router.delete("/measurements/{measurement_id}", status_code=204)
def delete_measurement(measurement_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(CalibrationMeasurement, measurement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    db.delete(row)
    db.commit()


@router.get("/summary")
def calibration_summary(db: Session = Depends(get_db)) -> dict:
    """Aggregate counts of measurements broken down by configuration."""
    from sqlalchemy import func
    rows = (
        db.query(
            CalibrationMeasurement.dem_source,
            CalibrationMeasurement.clutter_source,
            func.count(CalibrationMeasurement.id).label("count"),
            func.avg(CalibrationMeasurement.rssi_dbm).label("avg_rssi"),
        )
        .group_by(
            CalibrationMeasurement.dem_source,
            CalibrationMeasurement.clutter_source,
        )
        .all()
    )
    return {
        "groups": [
            {
                "dem_source": r.dem_source,
                "clutter_source": r.clutter_source,
                "count": r.count,
                "avg_rssi_dbm": float(r.avg_rssi) if r.avg_rssi is not None else None,
            }
            for r in rows
        ],
    }
