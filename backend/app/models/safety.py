import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String

from app.db.base import Base
from app.models.enums import (
    CameraSource,
    EventCategory,
    Severity,
    ShiftStatus,
    WorkerStatus,
)


class Site(Base):
    __tablename__ = "sites"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    location = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Device(Base):
    """Physical POV camera unit registered to a site.

    The per-shift worker binding lives on ``shifts.pov_device_id``.
    """

    __tablename__ = "devices"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    label = Column(String, nullable=False)  # e.g. "Cam-03"
    site_id = Column(String, ForeignKey("sites.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Worker(Base):
    __tablename__ = "workers"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_id = Column(String, ForeignKey("sites.id"), nullable=False)
    display_name = Column(String)  # local label only; never sent to external APIs
    appearance_embedding = Column(String)  # base64 — wall-cam re-ID (local only)
    # Deprecated/unused: face recognition was removed. Column kept nullable
    # so existing SQLite files keep opening; new code never writes it.
    face_embedding = Column(String)
    status = Column(SAEnum(WorkerStatus), default=WorkerStatus.ACTIVE)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime)
    total_violations = Column(Integer, default=0)
    total_compliant = Column(Integer, default=0)
    avg_msd_risk = Column(Float, default=0.0)


class Shift(Base):
    __tablename__ = "shifts"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    worker_id = Column(String, ForeignKey("workers.id"), nullable=False)
    site_id = Column(String, ForeignKey("sites.id"), nullable=False)
    date = Column(String, nullable=False)  # YYYY-MM-DD
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime)
    status = Column(SAEnum(ShiftStatus), default=ShiftStatus.IN_PROGRESS)
    pov_device_id = Column(String, ForeignKey("devices.id"), nullable=True)
    msd_risk_score = Column(Float)
    violation_count = Column(Integer, default=0)
    compliant_count = Column(Integer, default=0)


class SafetyEvent(Base):
    __tablename__ = "safety_events"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    shift_id = Column(String, ForeignKey("shifts.id"), nullable=False)
    worker_id = Column(String, ForeignKey("workers.id"), nullable=False)
    camera_source = Column(SAEnum(CameraSource), nullable=False)
    event_category = Column(SAEnum(EventCategory), nullable=False)
    violation_type = Column(String)
    severity = Column(SAEnum(Severity))
    video_timestamp = Column(Float)
    clip_path = Column(String)
    metadata_json = Column(String)  # JSON blob
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
