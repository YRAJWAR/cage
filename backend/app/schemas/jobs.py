from typing import Any, Literal

from pydantic import BaseModel


class JobSubmitOut(BaseModel):
    job_id: str
    status: Literal["PROCESSING"] = "PROCESSING"


class JobOut(BaseModel):
    job_id: str
    status: str
    events_written: int = 0
    error: str | None = None
    camera_source: str | None = None
    progress: float | None = None
    stage: str | None = None
    summary: dict[str, Any] | None = None
    posture_summary: dict[str, Any] | None = None
    job_dir: str | None = None
    shift_id: str | None = None
