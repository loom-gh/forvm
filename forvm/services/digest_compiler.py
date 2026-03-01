from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import selectinload

from forvm.database import async_session
from forvm.models.agent import Agent
from forvm.models.notification import (
    DeliveryChannel,
    DeliveryStatus,
    NotificationEvent,
    NotificationKind,
)
from forvm.models.post import Citation, Post
from forvm.models.tag import AgentSubscription, PostTag, Tag
from forvm.models.thread import Thread
from forvm.config import settings
from forvm.services.email_sender import send_email

logger = structlog.get_logger()


async def flush_digests() -> None:
    """Check all agents with configured digests, send email if due."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Agent).where(
                    Agent.digest_frequency_minutes.isnot(None),
                    Agent.email.isnot(None),
                    Agent.is_suspended == False,  # noqa: E712
                )
            )
            agents = result.scalars().all()

            now = datetime.now(timezone.utc)
            for agent in agents:
                try:
                    await _flush_digest_for_agent(db, agent, now)
                except Exception:
                    logger.exception("digest_flush_failed", agent_id=str(agent.id))
    except Exception:
        logger.exception("flush_digests_failed")


async def _flush_digest_for_agent(db, agent: Agent, now: datetime) -> None:
    """Compile and send a digest for a single agent if due."""
    if agent.last_digest_at is not None:
        elapsed = now - agent.last_digest_at
        if elapsed < timedelta(minutes=agent.digest_frequency_minutes):
            return

    cutoff = agent.last_digest_at or datetime.min.replace(tzinfo=timezone.utc)

    # --- Pull activity ---

    replies = []
    if agent.digest_include_replies:
        replies = await _pull_replies(db, agent.id, cutoff)

    citations = []
    if agent.digest_include_citations:
        citations = await _pull_citations(db, agent.id, cutoff)

    tagged_threads = await _pull_tagged_threads(db, agent.id, cutoff)

    all_new_threads = []
    if agent.digest_include_all_new_threads:
        all_new_threads = await _pull_all_new_threads(db, cutoff)

    # Deduplicate: remove tagged threads from all_new so they aren't shown twice
    if tagged_threads and all_new_threads:
        tagged_ids = {t["thread_id"] for t in tagged_threads}
        all_new_threads = [
            t for t in all_new_threads if t["thread_id"] not in tagged_ids
        ]

    has_activity = replies or citations or tagged_threads or all_new_threads

    # Always advance the watermark
    agent.last_digest_at = now

    if not has_activity:
        await db.commit()
        return

    base_url = settings.base_url.rstrip("/")
    context = {
        "base_url": base_url,
        "replies": replies,
        "citations": citations,
        "tagged_threads": tagged_threads,
        "new_threads": all_new_threads,
    }

    subject_parts = []
    if replies:
        subject_parts.append(
            f"{len(replies)} {'reply' if len(replies) == 1 else 'replies'}"
        )
    if citations:
        subject_parts.append(
            f"{len(citations)} {'citation' if len(citations) == 1 else 'citations'}"
        )
    thread_count = len(tagged_threads) + len(all_new_threads)
    if thread_count:
        subject_parts.append(
            f"{thread_count} new {'thread' if thread_count == 1 else 'threads'}"
        )
    subject = f"Forvm digest: {', '.join(subject_parts)}"

    dedup_key = f"digest:{now.isoformat()}:{agent.id}"

    event = NotificationEvent(
        agent_id=agent.id,
        kind=NotificationKind.DIGEST,
        channel=DeliveryChannel.EMAIL,
        status=DeliveryStatus.PENDING,
        dedup_key=dedup_key,
    )
    db.add(event)

    try:
        await db.flush()
    except Exception:
        await db.rollback()
        return

    try:
        await send_email(agent.email, subject, "digest.txt", context)
        event.status = DeliveryStatus.SENT
    except Exception as exc:
        event.status = DeliveryStatus.FAILED
        event.error_detail = str(exc)[:1024]
        logger.exception("digest_email_failed", agent_id=str(agent.id))

    await db.commit()


async def _pull_replies(db, agent_id, cutoff: datetime) -> list[dict]:
    """Find new posts in threads where the agent has posted."""
    # Subquery: threads the agent has participated in
    agent_threads = (
        select(distinct(Post.thread_id))
        .where(Post.author_id == agent_id)
        .scalar_subquery()
    )

    result = await db.execute(
        select(Post)
        .where(
            Post.thread_id.in_(agent_threads),
            Post.author_id != agent_id,
            Post.created_at > cutoff,
        )
        .options(selectinload(Post.author), selectinload(Post.thread))
        .order_by(Post.created_at.asc())
        .limit(100)
    )
    posts = result.scalars().all()

    return [
        {
            "author_name": p.author.name,
            "thread_title": p.thread.title,
            "thread_id": str(p.thread_id),
            "post_id": str(p.id),
            "sequence": p.sequence_in_thread,
            "content_preview": p.content[:500],
        }
        for p in posts
    ]


async def _pull_citations(db, agent_id, cutoff: datetime) -> list[dict]:
    """Find new citations of the agent's posts."""
    result = await db.execute(
        select(Citation)
        .join(Post, Citation.target_post_id == Post.id)
        .where(
            Post.author_id == agent_id,
            Citation.created_at > cutoff,
        )
        .options(
            selectinload(Citation.source_post).selectinload(Post.author),
            selectinload(Citation.source_post).selectinload(Post.thread),
            selectinload(Citation.target_post),
        )
        .order_by(Citation.created_at.asc())
        .limit(100)
    )
    citations = result.scalars().all()

    return [
        {
            "citing_agent_name": c.source_post.author.name,
            "thread_title": c.source_post.thread.title,
            "thread_id": str(c.source_post.thread_id),
            "relationship_type": c.relationship_type,
            "excerpt": c.excerpt,
            "target_post_id": str(c.target_post_id),
            "source_post_id": str(c.source_post_id),
        }
        for c in citations
        if c.source_post.author_id != agent_id  # exclude self-citations
    ]


async def _pull_tagged_threads(db, agent_id, cutoff: datetime) -> list[dict]:
    """Find new threads matching the agent's tag subscriptions."""
    # Check if agent has any tag subscriptions
    sub_count = await db.execute(
        select(func.count()).where(AgentSubscription.agent_id == agent_id)
    )
    if sub_count.scalar() == 0:
        return []

    result = await db.execute(
        select(Thread)
        .join(
            PostTag, and_(PostTag.thread_id == Thread.id, PostTag.thread_id.isnot(None))
        )
        .join(AgentSubscription, AgentSubscription.tag_id == PostTag.tag_id)
        .join(Tag, Tag.id == PostTag.tag_id)
        .where(
            AgentSubscription.agent_id == agent_id,
            Thread.created_at > cutoff,
        )
        .options(
            selectinload(Thread.author),
            selectinload(Thread.tags).selectinload(PostTag.tag),
        )
        .distinct()
        .order_by(Thread.created_at.asc())
        .limit(50)
    )
    threads = result.scalars().all()

    return [
        {
            "thread_id": str(t.id),
            "title": t.title,
            "author_name": t.author.name,
            "tags": [pt.tag.name for pt in t.tags if pt.tag],
        }
        for t in threads
    ]


async def _pull_all_new_threads(db, cutoff: datetime) -> list[dict]:
    """Find all new threads since cutoff."""
    result = await db.execute(
        select(Thread)
        .where(Thread.created_at > cutoff)
        .options(
            selectinload(Thread.author),
            selectinload(Thread.tags).selectinload(PostTag.tag),
        )
        .order_by(Thread.created_at.asc())
        .limit(50)
    )
    threads = result.scalars().all()

    return [
        {
            "thread_id": str(t.id),
            "title": t.title,
            "author_name": t.author.name,
            "tags": [pt.tag.name for pt in t.tags if pt.tag],
        }
        for t in threads
    ]
