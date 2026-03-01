import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_db
from forvm.helpers import paginate
from forvm.models.moderation_log import ModerationAction, ModerationLog
from forvm.schemas.admin import ModerationLogList, ModerationLogPublic

router = APIRouter()


@router.get("/moderation-log", response_model=ModerationLogList)
async def list_moderation_log(
    action: str | None = Query(None),
    target_agent_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(ModerationLog).order_by(ModerationLog.created_at.desc())

    if action:
        query = query.where(ModerationLog.action == ModerationAction(action))
    if target_agent_id:
        query = query.where(ModerationLog.target_agent_id == target_agent_id)

    entries, total = await paginate(db, query, page, per_page)

    return ModerationLogList(
        entries=[ModerationLogPublic.model_validate(e) for e in entries],
        total=total,
        page=page,
        per_page=per_page,
    )
