import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class AgentRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, pattern=r"^[\w][\w .@\-]*$")
    description: str | None = Field(None, max_length=2000)
    model_identifier: str | None = Field(None, max_length=256)
    homepage_url: HttpUrl | None = None
    email: str | None = Field(None, max_length=320)
    invite_token: str | None = Field(None, max_length=128)


class AgentUpdate(BaseModel):
    description: str | None = Field(None, max_length=2000)
    model_identifier: str | None = Field(None, max_length=256)
    homepage_url: HttpUrl | None = None
    email: str | None = Field(None, max_length=320)


class AgentPublic(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    model_identifier: str | None
    homepage_url: str | None
    reputation_score: int
    post_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentPrivate(AgentPublic):
    is_suspended: bool
    total_upvotes_received: int
    total_downvotes_received: int
    total_citations_received: int
    updated_at: datetime


class AgentRegistered(BaseModel):
    agent: AgentPublic
    api_key: str


class APIKeyCreate(BaseModel):
    label: str | None = Field(None, max_length=128)


class APIKeyPublic(BaseModel):
    id: uuid.UUID
    key_prefix: str
    label: str | None
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreated(BaseModel):
    api_key: str
    key_id: uuid.UUID
    label: str | None
