import uuid
from datetime import datetime

from pydantic import BaseModel


class ThreadHighlight(BaseModel):
    thread_id: str
    title: str
    reason: str


class DigestPublic(BaseModel):
    id: uuid.UUID
    summary_text: str
    thread_highlights: list[ThreadHighlight]
    new_post_count: int
    generated_at: datetime

    model_config = {"from_attributes": True}


class DigestList(BaseModel):
    digests: list[DigestPublic]
    total: int
    page: int
    per_page: int
