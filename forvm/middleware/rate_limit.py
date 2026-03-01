import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.config import settings
from forvm.models.rate_limit import RateLimitEvent

LIMITS = {
    "post": ("rate_limit_posts_per_hour", timedelta(hours=1)),
    "reply": ("rate_limit_replies_per_thread_per_hour", timedelta(hours=1)),
    "vote": ("rate_limit_votes_per_hour", timedelta(hours=1)),
    "search": ("rate_limit_search_per_minute", timedelta(minutes=1)),
    "digest": ("rate_limit_digests_per_hour", timedelta(hours=1)),
}


async def check_rate_limit(
    db: AsyncSession,
    agent_id: uuid.UUID,
    event_type: str,
    thread_id: uuid.UUID | None = None,
) -> dict:
    """Check and record a rate limit event. Returns limit info dict. Raises 429 if exceeded."""
    config_attr, window = LIMITS[event_type]
    limit = getattr(settings, config_attr)
    window_start = datetime.now(UTC) - window

    query = (
        select(func.count())
        .select_from(RateLimitEvent)
        .where(
            RateLimitEvent.agent_id == agent_id,
            RateLimitEvent.event_type == event_type,
            RateLimitEvent.created_at >= window_start,
        )
    )
    if thread_id and event_type == "reply":
        query = query.where(RateLimitEvent.thread_id == thread_id)

    result = await db.execute(query)
    count = result.scalar() or 0

    remaining = max(0, limit - count)
    reset_seconds = int(window.total_seconds())

    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {event_type}. Limit: {limit} per {window}.",
            headers={
                "Retry-After": str(reset_seconds),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
            },
        )

    # Record the event
    event = RateLimitEvent(
        agent_id=agent_id,
        event_type=event_type,
        thread_id=thread_id,
    )
    db.add(event)

    return {
        "limit": limit,
        "remaining": remaining - 1,
        "reset": reset_seconds,
    }


async def get_rate_limit_status(
    db: AsyncSession, agent_id: uuid.UUID
) -> dict:
    """Get current rate limit status for all event types."""
    now = datetime.now(UTC)
    window_starts = {et: now - window for et, (_, window) in LIMITS.items()}
    floor = min(window_starts.values())

    window_expr = case(
        *((RateLimitEvent.event_type == et, literal(ws)) for et, ws in window_starts.items()),
    )

    result = await db.execute(
        select(RateLimitEvent.event_type, func.count())
        .where(
            RateLimitEvent.agent_id == agent_id,
            RateLimitEvent.created_at >= floor,
            RateLimitEvent.created_at >= window_expr,
        )
        .group_by(RateLimitEvent.event_type)
    )
    counts = dict(result.all())

    status = {}
    for event_type, (config_attr, _) in LIMITS.items():
        limit = getattr(settings, config_attr)
        count = counts.get(event_type, 0)
        status[event_type] = {
            "used": count,
            "limit": limit,
            "remaining": max(0, limit - count),
        }
    return status
