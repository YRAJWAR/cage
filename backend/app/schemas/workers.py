from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import WorkerStatus


class WorkerRegister(BaseModel):
    site_id: str = Field(min_length=1)
    # Optional human label for local use only. Never sent to the Meta
    # Model API. Prefer opaque codes (e.g. "W-001") over real names.
    display_name: str = ""
    # Local re-ID embedding (base64). Stored locally, never sent externally.
    appearance_embedding: str = ""


class WorkerCheckin(BaseModel):
    """Link a worker to a POV device for today — opens a shift."""

    worker_id: str = Field(min_length=1)
    pov_device_id: str = Field(min_length=1)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class WorkerOut(BaseModel):
    worker_id: str
    display_name: str | None = None
    site_id: str | None = None
    status: WorkerStatus | None = None
    total_violations: int = 0
    total_compliant: int = 0
    avg_msd_risk: float = 0.0
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
