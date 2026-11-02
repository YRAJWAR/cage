from datetime import datetime

from pydantic import BaseModel, Field


class SiteCreate(BaseModel):
    name: str = Field(min_length=1)
    location: str = ""


class SiteOut(BaseModel):
    id: str
    name: str
    location: str | None = None
    created_at: datetime | None = None
