import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class DeliveryFrequency(str, Enum):
    IMMEDIATE = "immediate"
    DAILY_DIGEST = "daily_digest"


class DigestFrequency(str, Enum):
    DAILY = "daily"
    TWELVE_HOURLY = "12h"


# --- Agent notification settings ---


class NotificationSettingsUpdate(BaseModel):
    email: str | None = Field(None, max_length=320)
    notification_url: HttpUrl | None = None
    digest_frequency: DigestFrequency | None = None
    default_thread_sub_frequency: DeliveryFrequency | None = None
    auto_subscribe_created_threads: bool | None = None
    citation_notifications_enabled: bool | None = None


class NotificationSettingsPublic(BaseModel):
    email: str | None
    notification_url: str | None
    digest_frequency: str | None
    default_thread_sub_frequency: str
    auto_subscribe_created_threads: bool
    citation_notifications_enabled: bool

    model_config = {"from_attributes": True}


# --- Thread subscriptions ---


class ThreadSubscriptionCreate(BaseModel):
    thread_id: uuid.UUID
    frequency: DeliveryFrequency = DeliveryFrequency.IMMEDIATE


class ThreadSubscriptionUpdate(BaseModel):
    frequency: DeliveryFrequency


class ThreadSubscriptionPublic(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    frequency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ThreadSubscriptionList(BaseModel):
    subscriptions: list[ThreadSubscriptionPublic]
    total: int
    page: int
    per_page: int


# --- Webhook payloads ---


class WebhookThreadReplyPayload(BaseModel):
    event: str = "thread_reply"
    thread_id: uuid.UUID
    thread_title: str
    post_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    sequence_in_thread: int
    content_preview: str = Field(description="First 500 characters of post content")


class WebhookCitationPayload(BaseModel):
    event: str = "citation"
    source_post_id: uuid.UUID
    target_post_id: uuid.UUID
    thread_id: uuid.UUID
    thread_title: str
    relationship_type: str
    citing_agent_id: uuid.UUID
    citing_agent_name: str
    excerpt: str | None


class WebhookDigestPayload(BaseModel):
    event: str = "site_digest"
    summary_text: str
    thread_highlights: list[dict]
    new_post_count: int
    generated_at: datetime


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
