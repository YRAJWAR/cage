from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ShiftStatus
from app.schemas.events import EventOut


class ShiftClose(BaseModel):
    msd_risk_score: float | None = Field(default=None, ge=0)


class ShiftOut(BaseModel):
    shift_id: str
    worker_id: str
    site_id: str | None = None
    date: str
    status: ShiftStatus | None = None
    pov_device_id: str | None = None
    msd_risk_score: float | None = None
    violation_count: int = 0
    compliant_count: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    events: list[EventOut] = Field(default_factory=list)
