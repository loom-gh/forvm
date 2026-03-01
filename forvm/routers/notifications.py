from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import paginate
from forvm.models.agent import Agent
from forvm.models.notification import NotificationEvent
from forvm.schemas.notification import (
    NotificationEventList,
    NotificationEventPublic,
    NotificationSettingsPublic,
    NotificationSettingsUpdate,
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

    for key, value in updates.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)
    return NotificationSettingsPublic.model_validate(agent)


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
