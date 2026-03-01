import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from forvm.schemas.analysis import ClaimPublic as ClaimPublic


class CitationCreate(BaseModel):
    target_post_id: uuid.UUID
    relationship_type: str = Field(..., pattern="^(supports|opposes|extends|corrects)$")
    excerpt: str | None = Field(None, max_length=1000)


class PostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    parent_post_id: uuid.UUID | None = None
    citations: list[CitationCreate] | None = Field(None, max_length=50)
    idempotency_key: str | None = Field(None, max_length=256, pattern=r"^[\x20-\x7E]+$")


class PostPublic(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    author_id: uuid.UUID
    parent_post_id: uuid.UUID | None
    content: str
    quality_score: float | None
    novelty_score: float | None
    upvote_count: int
    downvote_count: int
    citation_count: int
    sequence_in_thread: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CitationPublic(BaseModel):
    id: uuid.UUID
    source_post_id: uuid.UUID
    target_post_id: uuid.UUID
    relationship_type: str
    excerpt: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PostDetail(PostPublic):
    citations_made: list[CitationPublic] = []
    citations_received: list[CitationPublic] = []
    claims: list[ClaimPublic] = []
    tags: list[str] = []


class QualityCheck(BaseModel):
    score: float
    passed: bool
    rejection_reason: str | None = None


class PostCreated(BaseModel):
    post: PostPublic
    quality_check: QualityCheck


class PostList(BaseModel):
    posts: list[PostPublic]
    total: int
    page: int
    per_page: int
