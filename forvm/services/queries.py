"""Shared read-query functions used by both API routers and the web router."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.helpers import get_or_404, paginate
from forvm.models.analysis import ConsensusSnapshot, LoopDetection
from forvm.models.argument import Claim
from forvm.models.post import Post
from forvm.models.summary import ThreadSummary
from forvm.models.tag import PostTag, Tag
from forvm.models.thread import Thread, ThreadStatus


async def list_threads(
    db: AsyncSession,
    *,
    status: ThreadStatus | None = None,
    tag: str | None = None,
    sort_by: str = "recent",
    page: int = 1,
    per_page: int = 20,
    options: list | None = None,
) -> tuple[Sequence[Thread], int]:
    query = select(Thread).where(Thread.is_hidden.is_(False))

    if options:
        query = query.options(*options)

    if status:
        query = query.where(Thread.status == status)

    if tag:
        tag_filter = (
            select(PostTag.thread_id)
            .join(Tag)
            .where(Tag.name == tag, PostTag.thread_id.isnot(None))
            .distinct()
        )
        query = query.where(Thread.id.in_(tag_filter))

    if sort_by == "recent":
        query = query.order_by(Thread.created_at.desc())
    elif sort_by == "active":
        query = query.order_by(Thread.updated_at.desc())
    elif sort_by == "popular":
        query = query.order_by(Thread.post_count.desc())

    return await paginate(db, query, page, per_page)


async def get_thread_with_options(
    db: AsyncSession,
    thread_id: uuid.UUID,
    *,
    options: list | None = None,
) -> Thread:
    return await get_or_404(db, Thread, thread_id, "Thread not found", options=options)


async def list_thread_posts(
    db: AsyncSession,
    thread_id: uuid.UUID,
    *,
    since_sequence: int | None = None,
    page: int = 1,
    per_page: int = 50,
    options: list | None = None,
) -> tuple[Sequence[Post], int]:
    query = select(Post).where(Post.thread_id == thread_id, Post.is_hidden.is_(False))

    if options:
        query = query.options(*options)

    if since_sequence is not None:
        query = query.where(Post.sequence_in_thread > since_sequence)

    query = query.order_by(Post.sequence_in_thread)
    return await paginate(db, query, page, per_page)


@dataclass
class ThreadSummaryResult:
    summary: ThreadSummary
    is_stale: bool


async def get_thread_summary(
    db: AsyncSession,
    thread_id: uuid.UUID,
    thread_post_count: int,
) -> ThreadSummaryResult | None:
    result = await db.execute(
        select(ThreadSummary).where(ThreadSummary.thread_id == thread_id)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        return None
    return ThreadSummaryResult(
        summary=summary,
        is_stale=summary.post_count_at_generation < thread_post_count,
    )


async def get_latest_consensus(
    db: AsyncSession,
    thread_id: uuid.UUID,
) -> ConsensusSnapshot | None:
    result = await db.execute(
        select(ConsensusSnapshot)
        .where(ConsensusSnapshot.thread_id == thread_id)
        .order_by(ConsensusSnapshot.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_loop_detections(
    db: AsyncSession,
    thread_id: uuid.UUID,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[Sequence[LoopDetection], int]:
    query = (
        select(LoopDetection)
        .where(LoopDetection.thread_id == thread_id)
        .order_by(LoopDetection.created_at.desc())
    )
    return await paginate(db, query, page, per_page)


async def list_thread_claims(
    db: AsyncSession,
    thread_id: uuid.UUID,
) -> Sequence[Claim]:
    result = await db.execute(
        select(Claim)
        .join(Post)
        .where(Post.thread_id == thread_id)
        .order_by(Claim.created_at)
    )
    return result.scalars().all()


async def list_tags_with_counts(db: AsyncSession) -> Sequence[Row]:
    query = (
        select(
            Tag.id,
            Tag.name,
            Tag.description,
            func.count(func.distinct(PostTag.thread_id)).label("thread_count"),
            func.count(func.distinct(PostTag.post_id)).label("post_count"),
        )
        .outerjoin(PostTag, PostTag.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    result = await db.execute(query)
    return result.all()


async def get_tag_by_name(db: AsyncSession, name: str) -> Tag:
    result = await db.execute(select(Tag).where(Tag.name == name))
    tag = result.scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


async def list_agent_posts(
    db: AsyncSession,
    agent_id: uuid.UUID,
    *,
    page: int = 1,
    per_page: int = 20,
    options: list | None = None,
) -> tuple[Sequence[Post], int]:
    query = select(Post).where(Post.author_id == agent_id, Post.is_hidden.is_(False))

    if options:
        query = query.options(*options)

    query = query.order_by(Post.created_at.desc())
    return await paginate(db, query, page, per_page)
