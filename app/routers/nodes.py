"""Node CRUD API endpoints."""

import os
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, RASTER_DIR
from app.models.node import Node
from app.models.coverage_site import CoverageSite
from app.models.schemas import NodeCreate, NodeUpdate

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
def list_nodes(db: Session = Depends(get_db)):
    nodes = db.query(Node).all()
    return [n.to_dict() for n in nodes]


@router.get("/{node_id}")
def get_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.to_dict()


@router.post("", status_code=201)
def create_node(payload: NodeCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(by_alias=True, exclude_none=False)
    if not data.get("id"):
        data["id"] = str(uuid4())
    node = Node.from_dict(data)
    db.add(node)
    db.commit()
    db.refresh(node)
    return node.to_dict()


@router.put("/{node_id}")
def update_node(node_id: str, payload: NodeUpdate, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    data = payload.model_dump(by_alias=True, exclude_unset=True)
    node.update_from_dict(data)
    db.commit()
    db.refresh(node)
    return node.to_dict()


@router.delete("/{node_id}", status_code=204)
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    # Also delete linked coverage site if any
    if node.site_id:
        site = db.query(CoverageSite).filter(CoverageSite.task_id == node.site_id).first()
        if site:
            raster_path = os.path.join(RASTER_DIR, f"{site.task_id}.tif")
            if os.path.exists(raster_path):
                os.remove(raster_path)
            db.delete(site)
    db.delete(node)
    db.commit()
    return None


@router.delete("", status_code=204)
def clear_all_nodes(db: Session = Depends(get_db)):
    db.query(Node).delete()
    db.commit()
    return None


@router.post("/batch", status_code=201)
def batch_create_nodes(payload: list[NodeCreate], db: Session = Depends(get_db)):
    created = []
    for item in payload:
        data = item.model_dump(by_alias=True, exclude_none=False)
        if not data.get("id"):
            data["id"] = str(uuid4())
        # Skip duplicates
        existing = db.query(Node).filter(Node.id == data["id"]).first()
        if existing:
            created.append(existing.to_dict())
            continue
        node = Node.from_dict(data)
        db.add(node)
        created.append(node.to_dict())
    db.commit()
    return created
