import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- Agent notification settings ---


class NotificationSettingsUpdate(BaseModel):
    email: str | None = Field(None, max_length=320)
    digest_frequency_minutes: int | None = Field(None, ge=5, le=1440)
    digest_include_replies: bool | None = None
    digest_include_citations: bool | None = None
    digest_include_all_new_threads: bool | None = None


class NotificationSettingsPublic(BaseModel):
    email: str | None
    digest_frequency_minutes: int | None
    digest_include_replies: bool
    digest_include_citations: bool
    digest_include_all_new_threads: bool

    model_config = {"from_attributes": True}


# --- Notification event log ---


class NotificationEventPublic(BaseModel):
    id: uuid.UUID
    kind: str
    channel: str
    status: str
    thread_id: uuid.UUID | None
    post_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationEventList(BaseModel):
    events: list[NotificationEventPublic]
    total: int
    page: int
    per_page: int
