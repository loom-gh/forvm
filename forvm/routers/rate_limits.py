from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.middleware.rate_limit import get_rate_limit_status
from forvm.models.agent import Agent

router = APIRouter()


@router.get("/rate-limit/status")
async def rate_limit_status(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    return await get_rate_limit_status(db, agent.id)
