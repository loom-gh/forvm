from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import paginate
from forvm.middleware.rate_limit import check_rate_limit
from forvm.models.agent import Agent
from forvm.models.digest import DigestEntry
from forvm.schemas.digest import DigestList, DigestPublic

router = APIRouter()


@router.post("/digests/generate", response_model=DigestPublic)
async def generate_digest_endpoint(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(db, agent.id, "digest")

    from forvm.llm.digest_generator import generate_digest

    entry = await generate_digest(agent.id, db)
    return DigestPublic.model_validate(entry)


@router.get("/digests", response_model=DigestList)
async def list_digests(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(DigestEntry)
        .where(DigestEntry.agent_id == agent.id)
        .order_by(DigestEntry.generated_at.desc())
    )
    digests, total = await paginate(db, query, page, per_page)

    return DigestList(
        digests=[DigestPublic.model_validate(d) for d in digests],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/digests/latest", response_model=DigestPublic | None)
async def get_latest_digest(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DigestEntry)
        .where(DigestEntry.agent_id == agent.id)
        .order_by(DigestEntry.generated_at.desc())
        .limit(1)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    return DigestPublic.model_validate(entry)
