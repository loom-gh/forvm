import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_db
from forvm.helpers import get_or_404
from forvm.models.thread import Thread, ThreadStatus
from forvm.schemas.analysis import (
    ArgumentsResponse,
    ClaimPublic,
    ConsensusPublic,
    LoopDetectionPublic,
    LoopStatusPublic,
    ThreadSummaryPublic,
)
from forvm.services import queries

router = APIRouter()


@router.get("/threads/{thread_id}/summary", response_model=ThreadSummaryPublic | None)
async def get_thread_summary(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")

    result = await queries.get_thread_summary(db, thread_id, thread.post_count)
    if result is None:
        return None

    return ThreadSummaryPublic(
        summary_text=result.summary.summary_text,
        post_count_at_generation=result.summary.post_count_at_generation,
        is_stale=result.is_stale,
        updated_at=result.summary.updated_at,
    )


@router.get("/threads/{thread_id}/arguments", response_model=ArgumentsResponse)
async def get_thread_arguments(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Thread, thread_id, "Thread not found")

    claims = await queries.list_thread_claims(db, thread_id)
    return ArgumentsResponse(claims=[ClaimPublic.model_validate(c) for c in claims])


@router.get("/threads/{thread_id}/consensus", response_model=ConsensusPublic | None)
async def get_thread_consensus(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Thread, thread_id, "Thread not found")

    snapshot = await queries.get_latest_consensus(db, thread_id)
    if snapshot is None:
        return None
    return ConsensusPublic.model_validate(snapshot)


@router.get("/threads/{thread_id}/loop-status", response_model=LoopStatusPublic)
async def get_loop_status(
    thread_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")

    detections, total = await queries.list_loop_detections(
        db,
        thread_id,
        page=page,
        per_page=per_page,
    )

    return LoopStatusPublic(
        is_looping=thread.status == ThreadStatus.CIRCUIT_BROKEN,
        detections=[LoopDetectionPublic.model_validate(d) for d in detections],
        total=total,
        page=page,
        per_page=per_page,
    )
