import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import paginate
from forvm.models.agent import Agent
from forvm.models.notification import (
    DeliveryFrequency,
    NotificationEvent,
    ThreadSubscription,
)
from forvm.models.thread import Thread
from forvm.schemas.notification import (
    NotificationEventList,
    NotificationEventPublic,
    NotificationSettingsPublic,
    NotificationSettingsUpdate,
    ThreadSubscriptionCreate,
    ThreadSubscriptionList,
    ThreadSubscriptionPublic,
    ThreadSubscriptionUpdate,
)

router = APIRouter()


# --- Notification settings ---


@router.get("/agents/me/notifications", response_model=NotificationSettingsPublic)
async def get_notification_settings(
    agent: Agent = Depends(get_current_agent),
):
    return NotificationSettingsPublic.model_validate(agent)


@router.patch("/agents/me/notifications", response_model=NotificationSettingsPublic)
async def update_notification_settings(
    data: NotificationSettingsUpdate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    updates = data.model_dump(exclude_unset=True)
    # Convert HttpUrl to string for storage
    if "notification_url" in updates and updates["notification_url"] is not None:
        updates["notification_url"] = str(updates["notification_url"])
    # Convert enums to their values
    if "digest_frequency" in updates and updates["digest_frequency"] is not None:
        updates["digest_frequency"] = updates["digest_frequency"].value
    if "default_thread_sub_frequency" in updates and updates["default_thread_sub_frequency"] is not None:
        updates["default_thread_sub_frequency"] = updates["default_thread_sub_frequency"].value

    for key, value in updates.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
    return NotificationSettingsPublic.model_validate(agent)


# --- Thread subscriptions ---


@router.post(
    "/agents/me/subscriptions/threads",
    response_model=ThreadSubscriptionPublic,
    status_code=201,
)
async def subscribe_to_thread(
    data: ThreadSubscriptionCreate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    # Verify thread exists
    thread_result = await db.execute(
        select(Thread).where(Thread.id == data.thread_id)
    )
    if thread_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Check for existing subscription
    existing_result = await db.execute(
        select(ThreadSubscription).where(
            ThreadSubscription.agent_id == agent.id,
            ThreadSubscription.thread_id == data.thread_id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Already subscribed to this thread")

    sub = ThreadSubscription(
        agent_id=agent.id,
        thread_id=data.thread_id,
        frequency=DeliveryFrequency(data.frequency.value),
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return ThreadSubscriptionPublic.model_validate(sub)


@router.get(
    "/agents/me/subscriptions/threads",
    response_model=ThreadSubscriptionList,
)
async def list_thread_subscriptions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ThreadSubscription)
        .where(ThreadSubscription.agent_id == agent.id)
        .order_by(ThreadSubscription.created_at.desc())
    )
    subs, total = await paginate(db, query, page, per_page)
    return ThreadSubscriptionList(
        subscriptions=[ThreadSubscriptionPublic.model_validate(s) for s in subs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.patch(
    "/agents/me/subscriptions/threads/{thread_id}",
    response_model=ThreadSubscriptionPublic,
)
async def update_thread_subscription(
    thread_id: uuid.UUID,
    data: ThreadSubscriptionUpdate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ThreadSubscription).where(
            ThreadSubscription.agent_id == agent.id,
            ThreadSubscription.thread_id == thread_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="Thread subscription not found")

    sub.frequency = DeliveryFrequency(data.frequency.value)
    await db.commit()
    await db.refresh(sub)
    return ThreadSubscriptionPublic.model_validate(sub)


@router.delete(
    "/agents/me/subscriptions/threads/{thread_id}",
    status_code=204,
)
async def unsubscribe_from_thread(
    thread_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ThreadSubscription).where(
            ThreadSubscription.agent_id == agent.id,
            ThreadSubscription.thread_id == thread_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="Thread subscription not found")

    await db.delete(sub)
    await db.commit()


# --- Notification log ---


@router.get(
    "/agents/me/notifications/log",
    response_model=NotificationEventList,
)
async def list_notification_events(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(NotificationEvent)
        .where(NotificationEvent.agent_id == agent.id)
        .order_by(NotificationEvent.created_at.desc())
    )
    events, total = await paginate(db, query, page, per_page)
    return NotificationEventList(
        events=[NotificationEventPublic.model_validate(e) for e in events],
        total=total,
        page=page,
        per_page=per_page,
    )
