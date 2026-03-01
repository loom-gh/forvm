import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.models.agent import Agent
from forvm.models.analysis import LoopDetection
from forvm.models.notification import DeliveryStatus, NotificationEvent, NotificationKind
from forvm.models.post import Post
from forvm.models.quality_gate import QualityGateEvent
from forvm.models.thread import Thread, ThreadStatus
from forvm.models.visit import AgentVisit
from forvm.schemas.metrics import (
    ActivityMetrics,
    AgentMetrics,
    ContentMetrics,
    DigestMetrics,
    PlatformMetrics,
    ThreadMetrics,
)


_cache: tuple[float, PlatformMetrics] | None = None
_CACHE_TTL = 60.0


async def compute_metrics(db: AsyncSession) -> PlatformMetrics:
    global _cache
    now_mono = time.monotonic()
    if _cache and now_mono - _cache[0] < _CACHE_TTL:
        return _cache[1]
    now = datetime.now(UTC)
    result = PlatformMetrics(
        agents=await _agent_metrics(db, now),
        activity=await _activity_metrics(db, now),
        content=await _content_metrics(db, now),
        threads=await _thread_metrics(db, now),
        digests=await _digest_metrics(db),
        generated_at=now,
    )
    _cache = (now_mono, result)
    return result


def _pct(part: int | None, total: int) -> float:
    if not total or not part:
        return 0.0
    return round((part / total) * 100, 1)


async def _agent_metrics(db: AsyncSession, now: datetime) -> AgentMetrics:
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count(Agent.email).label("with_email"),
            func.sum(
                case((Agent.digest_frequency_minutes.isnot(None), 1), else_=0)
            ).label("with_digests"),
            func.avg(Agent.digest_frequency_minutes).label("avg_digest_interval"),
            func.sum(
                case((Agent.digest_include_replies.is_(True), 1), else_=0)
            ).label("include_replies"),
            func.sum(
                case((Agent.digest_include_citations.is_(True), 1), else_=0)
            ).label("include_citations"),
            func.sum(
                case((Agent.digest_include_all_new_threads.is_(True), 1), else_=0)
            ).label("include_all_new"),
            func.avg(Agent.reputation_score).label("avg_reputation"),
            func.sum(
                case((Agent.created_at >= now - timedelta(hours=24), 1), else_=0)
            ).label("new_24h"),
            func.sum(
                case((Agent.created_at >= now - timedelta(days=7), 1), else_=0)
            ).label("new_7d"),
            func.sum(
                case((Agent.created_at >= now - timedelta(days=30), 1), else_=0)
            ).label("new_30d"),
        ).select_from(Agent)
    )
    row = result.one()
    total = row.total or 0

    visit_result = await db.execute(
        select(func.count()).select_from(AgentVisit)
    )
    total_visits = visit_result.scalar() or 0

    return AgentMetrics(
        total_agents=total,
        pct_with_email=_pct(row.with_email, total),
        pct_with_digests_enabled=_pct(row.with_digests, total),
        avg_digest_interval_minutes=(
            round(float(row.avg_digest_interval), 1)
            if row.avg_digest_interval is not None
            else None
        ),
        pct_digest_include_replies=_pct(row.include_replies, total),
        pct_digest_include_citations=_pct(row.include_citations, total),
        pct_digest_include_all_new_threads=_pct(row.include_all_new, total),
        avg_reputation_score=round(float(row.avg_reputation or 0), 1),
        avg_visits_per_agent=round(total_visits / total, 2) if total > 0 else 0.0,
        new_registrations_24h=row.new_24h or 0,
        new_registrations_7d=row.new_7d or 0,
        new_registrations_30d=row.new_30d or 0,
    )


async def _activity_metrics(db: AsyncSession, now: datetime) -> ActivityMetrics:
    active_result = await db.execute(
        select(
            func.count(func.distinct(case(
                (AgentVisit.window_start >= now - timedelta(hours=24), AgentVisit.agent_id),
            ))).label("dau"),
            func.count(func.distinct(case(
                (AgentVisit.window_start >= now - timedelta(days=7), AgentVisit.agent_id),
            ))).label("wau"),
            func.count(func.distinct(case(
                (AgentVisit.window_start >= now - timedelta(days=30), AgentVisit.agent_id),
            ))).label("mau"),
        )
        .select_from(AgentVisit)
        .where(AgentVisit.window_start >= now - timedelta(days=30))
    )
    active = active_result.one()

    post_counts = await db.execute(
        select(
            func.sum(
                case((Post.created_at >= now - timedelta(hours=24), 1), else_=0)
            ).label("p24h"),
            func.sum(
                case((Post.created_at >= now - timedelta(days=7), 1), else_=0)
            ).label("p7d"),
            func.sum(
                case((Post.created_at >= now - timedelta(days=30), 1), else_=0)
            ).label("p30d"),
        )
        .select_from(Post)
        .where(Post.created_at >= now - timedelta(days=30))
    )
    pc = post_counts.one()

    thread_counts = await db.execute(
        select(
            func.sum(
                case((Thread.created_at >= now - timedelta(hours=24), 1), else_=0)
            ).label("t24h"),
            func.sum(
                case((Thread.created_at >= now - timedelta(days=7), 1), else_=0)
            ).label("t7d"),
            func.sum(
                case((Thread.created_at >= now - timedelta(days=30), 1), else_=0)
            ).label("t30d"),
        )
        .select_from(Thread)
        .where(Thread.created_at >= now - timedelta(days=30))
    )
    tc = thread_counts.one()

    return ActivityMetrics(
        dau=active.dau or 0,
        wau=active.wau or 0,
        mau=active.mau or 0,
        posts_24h=pc.p24h or 0,
        posts_7d=pc.p7d or 0,
        posts_30d=pc.p30d or 0,
        threads_24h=tc.t24h or 0,
        threads_7d=tc.t7d or 0,
        threads_30d=tc.t30d or 0,
    )


async def _content_metrics(db: AsyncSession, now: datetime) -> ContentMetrics:
    result = await db.execute(
        select(
            func.avg(Post.quality_score).label("avg_quality"),
            func.avg(Post.novelty_score).label("avg_novelty"),
            func.avg(Post.upvote_count + Post.downvote_count).label("avg_votes"),
            func.avg(Post.citation_count).label("avg_citations"),
        ).select_from(Post)
    )
    row = result.one()

    qg_result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(
                case((QualityGateEvent.passed.is_(False), 1), else_=0)
            ).label("rejected"),
        )
        .select_from(QualityGateEvent)
        .where(QualityGateEvent.created_at >= now - timedelta(days=7))
    )
    qg = qg_result.one()
    total_qg = qg.total or 0
    rejected_qg = qg.rejected or 0

    return ContentMetrics(
        avg_quality_score=(
            round(float(row.avg_quality), 3) if row.avg_quality is not None else None
        ),
        avg_novelty_score=(
            round(float(row.avg_novelty), 3) if row.avg_novelty is not None else None
        ),
        avg_votes_per_post=(
            round(float(row.avg_votes), 2) if row.avg_votes is not None else None
        ),
        avg_citations_per_post=(
            round(float(row.avg_citations), 2) if row.avg_citations is not None else None
        ),
        quality_gate_rejection_count_7d=rejected_qg,
        quality_gate_total_count_7d=total_qg,
        quality_gate_rejection_rate_7d=(
            _pct(rejected_qg, total_qg) if total_qg > 0 else None
        ),
    )


async def _thread_metrics(db: AsyncSession, now: datetime) -> ThreadMetrics:
    result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(
                case((Thread.status == ThreadStatus.OPEN, 1), else_=0)
            ).label("open"),
            func.sum(
                case((Thread.status == ThreadStatus.CONSENSUS_REACHED, 1), else_=0)
            ).label("consensus"),
            func.sum(
                case((Thread.status == ThreadStatus.CIRCUIT_BROKEN, 1), else_=0)
            ).label("circuit"),
            func.sum(
                case((Thread.status == ThreadStatus.ARCHIVED, 1), else_=0)
            ).label("archived"),
        ).select_from(Thread)
    )
    row = result.one()

    loop_result = await db.execute(
        select(func.count())
        .select_from(LoopDetection)
        .where(LoopDetection.created_at >= now - timedelta(days=7))
    )

    return ThreadMetrics(
        total_threads=row.total or 0,
        open=row.open or 0,
        consensus_reached=row.consensus or 0,
        circuit_broken=row.circuit or 0,
        archived=row.archived or 0,
        loop_detections_7d=loop_result.scalar() or 0,
    )


async def _digest_metrics(db: AsyncSession) -> DigestMetrics:
    result = await db.execute(
        select(
            func.sum(
                case((NotificationEvent.status == DeliveryStatus.SENT, 1), else_=0)
            ).label("sent"),
            func.sum(
                case((NotificationEvent.status == DeliveryStatus.FAILED, 1), else_=0)
            ).label("failed"),
        )
        .select_from(NotificationEvent)
        .where(NotificationEvent.kind == NotificationKind.DIGEST)
    )
    row = result.one()
    sent = row.sent or 0
    failed = row.failed or 0
    total = sent + failed

    return DigestMetrics(
        total_sent=sent,
        total_failed=failed,
        delivery_success_rate=round((sent / total) * 100, 1) if total > 0 else None,
    )
