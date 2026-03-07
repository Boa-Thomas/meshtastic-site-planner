"""SQLAlchemy ORM model for the coverage_sites table."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.database import Base


class CoverageSite(Base):
    __tablename__ = "coverage_sites"

    task_id = Column(String(36), primary_key=True)
    params = Column(Text, nullable=False)  # Full SplatParams as JSON
    raster_path = Column(String(512), nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "taskId": self.task_id,
            "params": self.params,
            "rasterPath": self.raster_path,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
