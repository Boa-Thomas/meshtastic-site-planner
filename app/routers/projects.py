"""Project export/import API endpoints."""

import base64
import gzip
import json
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db, RASTER_DIR
from app.models.node import Node
from app.models.coverage_site import CoverageSite

router = APIRouter(prefix="/api/project", tags=["project"])


@router.get("/export")
def export_project(db: Session = Depends(get_db)):
    nodes = db.query(Node).all()
    sites = db.query(CoverageSite).all()

    # Build nodes list (without siteId, same as client export)
    nodes_data = []
    for n in nodes:
        d = n.to_dict()
        node_site_id = d.pop("siteId", None)
        nodes_data.append({"data": d, "siteId": node_site_id})

    # Build sites list with base64-encoded rasters
    sites_data = []
    for s in sites:
        raster_path = os.path.join(RASTER_DIR, f"{s.task_id}.tif")
        raster_b64 = ""
        if os.path.exists(raster_path):
            with open(raster_path, "rb") as f:
                raster_b64 = base64.b64encode(f.read()).decode("ascii")

        # Find the node that references this site
        linked_node = next((nd for nd in nodes_data if nd["siteId"] == s.task_id), None)
        sites_data.append({
            "taskId": s.task_id,
            "params": json.loads(s.params) if isinstance(s.params, str) else s.params,
            "nodeId": linked_node["data"]["id"] if linked_node else None,
            "rasterBase64": raster_b64,
        })

    from datetime import datetime, timezone
    project = {
        "version": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "appName": "meshtastic-site-planner",
        "nodes": [nd["data"] for nd in nodes_data],
        "sites": sites_data,
        "splatParams": {},
        "desConfig": {},
        "map": {"center": [-26.82, -49.27], "zoom": 10, "baseLayer": "OSM"},
    }

    compressed = gzip.compress(json.dumps(project).encode("utf-8"))
    return Response(
        content=compressed,
        media_type="application/gzip",
        headers={
            "Content-Disposition": 'attachment; filename="meshtastic-project-export.json.gz"',
        },
    )


@router.post("/import")
async def import_project(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        raw = await file.read()
        # Try to decompress; if it fails, treat as plain JSON
        try:
            text = gzip.decompress(raw).decode("utf-8")
        except gzip.BadGzipFile:
            text = raw.decode("utf-8")

        data = json.loads(text)
        if data.get("version") != 1 or data.get("appName") != "meshtastic-site-planner":
            raise HTTPException(status_code=400, detail="Invalid project file format")

        # Clear existing data
        for site in db.query(CoverageSite).all():
            raster_path = os.path.join(RASTER_DIR, f"{site.task_id}.tif")
            if os.path.exists(raster_path):
                os.remove(raster_path)
        db.query(CoverageSite).delete()
        db.query(Node).delete()

        # Import nodes
        nodes_imported = 0
        if isinstance(data.get("nodes"), list):
            for node_data in data["nodes"]:
                node = Node.from_dict(node_data)
                db.add(node)
                nodes_imported += 1

        # Import sites
        sites_imported = 0
        if isinstance(data.get("sites"), list):
            for site_data in data["sites"]:
                task_id = site_data["taskId"]
                params = site_data.get("params", {})
                raster_b64 = site_data.get("rasterBase64", "")

                if raster_b64:
                    raster_bytes = base64.b64decode(raster_b64)
                    raster_path = os.path.join(RASTER_DIR, f"{task_id}.tif")
                    os.makedirs(RASTER_DIR, exist_ok=True)
                    with open(raster_path, "wb") as f:
                        f.write(raster_bytes)

                    site = CoverageSite(
                        task_id=task_id,
                        params=json.dumps(params) if not isinstance(params, str) else params,
                        raster_path=raster_path,
                    )
                    db.add(site)
                    sites_imported += 1

                    # Re-link node → site
                    node_id = site_data.get("nodeId")
                    if node_id:
                        node = db.query(Node).filter(Node.id == node_id).first()
                        if node:
                            node.site_id = task_id

        db.commit()
        return {"nodesImported": nodes_imported, "sitesImported": sites_imported}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")
