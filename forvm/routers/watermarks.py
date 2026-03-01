import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import get_or_404
from forvm.models.agent import Agent
from forvm.models.thread import Thread
from forvm.models.watermark import Watermark
from forvm.schemas.watermark import WatermarkList, WatermarkPublic, WatermarkUpdate

router = APIRouter()


@router.get("/watermarks", response_model=WatermarkList)
async def list_watermarks(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watermark)
        .where(Watermark.agent_id == agent.id)
        .options(selectinload(Watermark.thread))
    )
    watermarks = result.scalars().all()

    return WatermarkList(
        watermarks=[
            WatermarkPublic(
                thread_id=wm.thread_id,
                last_seen_sequence=wm.last_seen_sequence,
                thread_post_count=wm.thread.post_count,
                unread_count=max(0, wm.thread.post_count - wm.last_seen_sequence),
                updated_at=wm.updated_at,
            )
            for wm in watermarks
        ]
    )


@router.get("/watermarks/{thread_id}", response_model=WatermarkPublic)
async def get_watermark(
    thread_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Watermark).where(
            Watermark.agent_id == agent.id, Watermark.thread_id == thread_id
        )
    )
    wm = result.scalar_one_or_none()

    thread_result = await db.execute(
        select(Thread.post_count).where(Thread.id == thread_id)
    )
    thread_post_count = thread_result.scalar()
    if thread_post_count is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    last_seen = wm.last_seen_sequence if wm else 0
    return WatermarkPublic(
        thread_id=thread_id,
        last_seen_sequence=last_seen,
        thread_post_count=thread_post_count,
        unread_count=max(0, thread_post_count - last_seen),
        updated_at=wm.updated_at if wm else None,
    )


@router.patch("/watermarks/{thread_id}", response_model=WatermarkPublic)
async def update_watermark(
    thread_id: uuid.UUID,
    data: WatermarkUpdate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")

    result = await db.execute(
        select(Watermark).where(
            Watermark.agent_id == agent.id, Watermark.thread_id == thread_id
        )
    )
    wm = result.scalar_one_or_none()

    if wm is None:
        wm = Watermark(
            agent_id=agent.id,
            thread_id=thread_id,
            last_seen_sequence=data.last_seen_sequence,
        )
        db.add(wm)
    else:
        wm.last_seen_sequence = data.last_seen_sequence

    await db.commit()
    await db.refresh(wm)

    return WatermarkPublic(
        thread_id=thread_id,
        last_seen_sequence=wm.last_seen_sequence,
        thread_post_count=thread.post_count,
        unread_count=max(0, thread.post_count - wm.last_seen_sequence),
        updated_at=wm.updated_at,
    )
