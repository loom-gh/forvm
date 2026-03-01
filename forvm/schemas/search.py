import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    scope: str = Field("both", pattern="^(posts|threads|both)$")
    tags: list[str] | None = None
    limit: int = Field(20, ge=1, le=100)
    min_similarity: float = Field(0.0, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    type: str
    id: uuid.UUID
    title: str | None = None
    content_snippet: str | None = None
    similarity_score: float
    thread_id: uuid.UUID | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
