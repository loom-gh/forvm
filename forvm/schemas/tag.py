import uuid
from datetime import datetime

from pydantic import BaseModel


class TagPublic(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TagList(BaseModel):
    tags: list[TagPublic]
    total: int
    page: int
    per_page: int


class SubscriptionCreate(BaseModel):
    tag_id: uuid.UUID


class SubscriptionPublic(BaseModel):
    id: uuid.UUID
    tag_id: uuid.UUID
    tag_name: str
    created_at: datetime
