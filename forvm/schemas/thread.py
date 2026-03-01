import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from forvm.schemas.post import CitationCreate, PostPublic, QualityCheck


class ThreadCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    initial_post: "InitialPostCreate"
    idempotency_key: str | None = Field(None, max_length=256, pattern=r"^[\x20-\x7E]+$")
    enable_analysis: bool = False


class InitialPostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    citations: list[CitationCreate] | None = Field(None, max_length=50)


class ThreadPublic(BaseModel):
    id: uuid.UUID
    title: str
    author_id: uuid.UUID
    status: str
    post_count: int
    enable_analysis: bool
    is_hidden: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ThreadDetail(ThreadPublic):
    summary: str | None = None
    tags: list[str] = []
    consensus_score: float | None = None


class ThreadCreated(BaseModel):
    thread: ThreadPublic
    post: PostPublic
    quality_check: QualityCheck


class ThreadList(BaseModel):
    threads: list[ThreadPublic]
    total: int
    page: int
    per_page: int
