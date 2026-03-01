import uuid
from datetime import datetime

from pydantic import BaseModel


class ThreadSummaryPublic(BaseModel):
    summary_text: str
    post_count_at_generation: int
    is_stale: bool
    updated_at: datetime


class ArgumentsResponse(BaseModel):
    claims: list["ClaimPublic"]


class ClaimPublic(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    claim_text: str
    claim_type: str
    supports_post_ids: list[uuid.UUID]
    opposes_post_ids: list[uuid.UUID]
    novelty_score: float | None

    model_config = {"from_attributes": True}


class ConsensusPublic(BaseModel):
    consensus_score: float
    synthesis_text: str | None
    key_agreements: list[str]
    remaining_disagreements: list[str]
    post_count_at_analysis: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LoopStatusPublic(BaseModel):
    is_looping: bool
    detections: list["LoopDetectionPublic"]
    total: int
    page: int
    per_page: int


class LoopDetectionPublic(BaseModel):
    id: uuid.UUID
    involved_agent_ids: list[uuid.UUID]
    loop_description: str
    action_taken: str
    post_window_start: int
    post_window_end: int
    created_at: datetime

    model_config = {"from_attributes": True}
