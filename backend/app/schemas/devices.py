from datetime import datetime

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    label: str = Field(min_length=1)
    site_id: str = Field(min_length=1)


class DeviceOut(BaseModel):
    id: str
    label: str
    site_id: str
    created_at: datetime | None = None
