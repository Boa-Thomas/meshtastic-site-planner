"""Coverage site persistence API endpoints."""

import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db, RASTER_DIR
from app.models.coverage_site import CoverageSite

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("")
def list_sites(db: Session = Depends(get_db)):
    sites = db.query(CoverageSite).all()
    return [s.to_dict() for s in sites]


@router.get("/{task_id}/raster")
def get_site_raster(task_id: str, db: Session = Depends(get_db)):
    site = db.query(CoverageSite).filter(CoverageSite.task_id == task_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    raster_path = os.path.join(RASTER_DIR, f"{task_id}.tif")
    if not os.path.exists(raster_path):
        raise HTTPException(status_code=404, detail="Raster file not found")
    return FileResponse(
        raster_path,
        media_type="image/tiff",
        headers={"Content-Disposition": f"attachment; filename={task_id}.tif"},
    )


@router.delete("/{task_id}", status_code=204)
def delete_site(task_id: str, db: Session = Depends(get_db)):
    site = db.query(CoverageSite).filter(CoverageSite.task_id == task_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    raster_path = os.path.join(RASTER_DIR, f"{task_id}.tif")
    if os.path.exists(raster_path):
        os.remove(raster_path)
    db.delete(site)
    db.commit()
    return None


@router.delete("", status_code=204)
def clear_all_sites(db: Session = Depends(get_db)):
    sites = db.query(CoverageSite).all()
    for site in sites:
        raster_path = os.path.join(RASTER_DIR, f"{site.task_id}.tif")
        if os.path.exists(raster_path):
            os.remove(raster_path)
    db.query(CoverageSite).delete()
    db.commit()
    return None
