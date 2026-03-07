"""
SQLAlchemy database engine, session factory, and initialization utilities.

Uses SQLite for persistent storage of nodes and coverage sites.
The database path is configurable via the DATABASE_PATH environment variable.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_PATH = os.environ.get("DATABASE_PATH", "app/data/planner.db")
DATA_DIR = os.path.dirname(DATABASE_PATH)
RASTER_DIR = os.path.join(DATA_DIR, "rasters")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RASTER_DIR, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist."""
    from app.models.node import Node  # noqa: F401
    from app.models.coverage_site import CoverageSite  # noqa: F401
    Base.metadata.create_all(bind=engine)
