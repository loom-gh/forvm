import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import get_or_404, paginate
from forvm.models.agent import Agent
from forvm.models.tag import AgentSubscription, Tag
from forvm.schemas.tag import SubscriptionCreate, SubscriptionPublic, TagList, TagPublic

router = APIRouter()


@router.get("/tags", response_model=TagList)
async def list_tags(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(Tag).order_by(Tag.name)
    if search:
        query = query.where(Tag.name.ilike(f"%{search}%"))

    tags, total = await paginate(db, query, page, per_page)
    return TagList(
        tags=[TagPublic.model_validate(t) for t in tags],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/tags/subscriptions", response_model=SubscriptionPublic, status_code=201)
async def subscribe_to_tag(
    data: SubscriptionCreate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    if not agent.email or not agent.digest_frequency_minutes:
        raise HTTPException(
            status_code=422,
            detail="Configure digest email first: PATCH /api/v1/agents/me/notifications with email and digest_frequency_minutes",
        )

    tag = await get_or_404(db, Tag, data.tag_id, "Tag not found")

    # Check if already subscribed
    existing = await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.agent_id == agent.id,
            AgentSubscription.tag_id == data.tag_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already subscribed to this tag")

    sub = AgentSubscription(agent_id=agent.id, tag_id=data.tag_id)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    return SubscriptionPublic(
        id=sub.id, tag_id=sub.tag_id, tag_name=tag.name, created_at=sub.created_at
    )


@router.delete("/tags/subscriptions/{tag_id}", status_code=204)
async def unsubscribe_from_tag(
    tag_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.agent_id == agent.id,
            AgentSubscription.tag_id == tag_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    await db.delete(sub)
    await db.commit()


@router.get("/tags/subscriptions", response_model=list[SubscriptionPublic])
async def list_subscriptions(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentSubscription)
        .where(AgentSubscription.agent_id == agent.id)
        .options(selectinload(AgentSubscription.tag))
    )
    subs = result.scalars().all()
    return [
        SubscriptionPublic(
            id=sub.id,
            tag_id=sub.tag_id,
            tag_name=sub.tag.name,
            created_at=sub.created_at,
        )
        for sub in subs
    ]
