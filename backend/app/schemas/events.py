from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import CameraSource, EventCategory, Severity


class EventIngest(BaseModel):
    """One safety event written by an ML pipeline."""

    shift_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    camera_source: CameraSource
    event_category: EventCategory
    violation_type: str | None = None
    severity: Severity | None = None
    video_timestamp: float = 0.0
    clip_path: str | None = None
    metadata: dict[str, Any] | None = None


class EventOut(BaseModel):
    event_id: str
    shift_id: str
    worker_id: str
    camera_source: CameraSource | None = None
    event_category: EventCategory | None = None
    violation_type: str | None = None
    severity: Severity | None = None
    video_timestamp: float | None = None
    clip_path: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
