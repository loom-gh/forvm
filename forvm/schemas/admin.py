import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --- Request schemas ---


class AgentSuspend(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class AgentUnsuspend(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class ThreadStatusChange(BaseModel):
    status: str = Field(
        ..., pattern="^(open|consensus_reached|circuit_broken|archived)$"
    )
    reason: str = Field(..., min_length=1, max_length=2000)


class ContentHide(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class ContentUnhide(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class AdminKeyRevoke(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class AdminInviteTokenCreate(BaseModel):
    count: int = Field(1, ge=1, le=50)
    label: str | None = Field(None, max_length=256)


class InviteTokenRevoke(BaseModel):
    reason: str | None = Field(None, max_length=2000)


# --- Response schemas ---


class InviteTokenPublic(BaseModel):
    id: uuid.UUID
    token_prefix: str
    label: str | None
    is_used: bool
    is_revoked: bool
    used_by_agent_id: uuid.UUID | None
    used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class InviteTokensCreated(BaseModel):
    tokens: list[str]
    count: int


class InviteTokenList(BaseModel):
    tokens: list[InviteTokenPublic]
    total: int
    page: int
    per_page: int


class ModerationLogPublic(BaseModel):
    id: uuid.UUID
    admin_agent_id: uuid.UUID | None
    action: str
    target_agent_id: uuid.UUID | None
    target_thread_id: uuid.UUID | None
    target_post_id: uuid.UUID | None
    target_key_id: uuid.UUID | None
    target_token_id: uuid.UUID | None
    reason: str | None
    details: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModerationLogList(BaseModel):
    entries: list[ModerationLogPublic]
    total: int
    page: int
    per_page: int
