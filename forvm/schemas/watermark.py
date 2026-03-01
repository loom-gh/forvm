import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WatermarkPublic(BaseModel):
    thread_id: uuid.UUID
    last_seen_sequence: int
    thread_post_count: int | None = None
    unread_count: int | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WatermarkUpdate(BaseModel):
    last_seen_sequence: int = Field(..., ge=0)


class WatermarkList(BaseModel):
    watermarks: list[WatermarkPublic]
