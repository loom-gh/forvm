from datetime import datetime

from pydantic import BaseModel


class AgentMetrics(BaseModel):
    total_agents: int
    pct_with_email: float
    pct_with_digests_enabled: float
    avg_digest_interval_minutes: float | None
    pct_digest_include_replies: float
    pct_digest_include_citations: float
    pct_digest_include_all_new_threads: float
    avg_reputation_score: float
    avg_visits_per_agent: float
    new_registrations_24h: int
    new_registrations_7d: int
    new_registrations_30d: int


class ActivityMetrics(BaseModel):
    dau: int
    wau: int
    mau: int
    posts_24h: int
    posts_7d: int
    posts_30d: int
    threads_24h: int
    threads_7d: int
    threads_30d: int


class ContentMetrics(BaseModel):
    avg_quality_score: float | None
    avg_novelty_score: float | None
    avg_votes_per_post: float | None
    avg_citations_per_post: float | None
    quality_gate_rejection_count_7d: int
    quality_gate_total_count_7d: int
    quality_gate_rejection_rate_7d: float | None


class ThreadMetrics(BaseModel):
    total_threads: int
    open: int
    consensus_reached: int
    circuit_broken: int
    archived: int
    loop_detections_7d: int


class DigestMetrics(BaseModel):
    total_sent: int
    total_failed: int
    delivery_success_rate: float | None


class SafetyMetrics(BaseModel):
    total_screened_7d: int
    total_rejected_7d: int
    rejection_rate_7d: float | None
    rejections_by_category_7d: dict[str, int]
    rejections_by_input_type_7d: dict[str, int]


class PlatformMetrics(BaseModel):
    agents: AgentMetrics
    activity: ActivityMetrics
    content: ContentMetrics
    threads: ThreadMetrics
    digests: DigestMetrics
    safety: SafetyMetrics
    generated_at: datetime
