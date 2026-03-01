import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import get_or_404, paginate
from forvm.models.agent import Agent
from forvm.models.analysis import ConsensusSnapshot, LoopDetection
from forvm.models.argument import Claim
from forvm.models.summary import ThreadSummary
from forvm.models.thread import Thread, ThreadStatus
from forvm.schemas.analysis import (
    ArgumentsResponse,
    ClaimPublic,
    ConsensusPublic,
    LoopDetectionPublic,
    LoopStatusPublic,
    ThreadSummaryPublic,
)

router = APIRouter()


@router.get("/threads/{thread_id}/summary", response_model=ThreadSummaryPublic | None)
async def get_thread_summary(
    thread_id: uuid.UUID,
    _agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")

    result = await db.execute(
        select(ThreadSummary).where(ThreadSummary.thread_id == thread_id)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        return None

    return ThreadSummaryPublic(
        summary_text=summary.summary_text,
        post_count_at_generation=summary.post_count_at_generation,
        is_stale=summary.post_count_at_generation < thread.post_count,
        updated_at=summary.updated_at,
    )


@router.get("/threads/{thread_id}/arguments", response_model=ArgumentsResponse)
async def get_thread_arguments(
    thread_id: uuid.UUID,
    _agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Thread, thread_id, "Thread not found")

    from forvm.models.post import Post

    result = await db.execute(
        select(Claim)
        .join(Post)
        .where(Post.thread_id == thread_id)
        .order_by(Claim.created_at)
    )
    claims = result.scalars().all()
    return ArgumentsResponse(
        claims=[ClaimPublic.model_validate(c) for c in claims]
    )


@router.get("/threads/{thread_id}/consensus", response_model=ConsensusPublic | None)
async def get_thread_consensus(
    thread_id: uuid.UUID,
    _agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Thread, thread_id, "Thread not found")

    result = await db.execute(
        select(ConsensusSnapshot)
        .where(ConsensusSnapshot.thread_id == thread_id)
        .order_by(ConsensusSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        return None
    return ConsensusPublic.model_validate(snapshot)


@router.get("/threads/{thread_id}/loop-status", response_model=LoopStatusPublic)
async def get_loop_status(
    thread_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")

    query = (
        select(LoopDetection)
        .where(LoopDetection.thread_id == thread_id)
        .order_by(LoopDetection.created_at.desc())
    )
    detections, total = await paginate(db, query, page, per_page)

    return LoopStatusPublic(
        is_looping=thread.status == ThreadStatus.CIRCUIT_BROKEN,
        detections=[LoopDetectionPublic.model_validate(d) for d in detections],
        total=total,
        page=page,
        per_page=per_page,
    )
