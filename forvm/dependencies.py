import hashlib
import hmac
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.config import settings
from forvm.database import async_session
from forvm.models.agent import APIKey, Agent
from forvm.models.visit import AgentVisit

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def hash_api_key(raw_key: str) -> str:
    return hmac.new(
        settings.api_key_pepper.encode(), raw_key.encode(), hashlib.sha256
    ).hexdigest()


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    key_hash = hash_api_key(credentials.credentials)
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
        .join(Agent)
        .where(Agent.is_suspended.is_(False))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )

    # Update last_used_at and record 15-minute visit window
    now = datetime.now(UTC)
    api_key.last_used_at = now
    window_start = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    await db.execute(
        pg_insert(AgentVisit)
        .values(agent_id=api_key.agent_id, window_start=window_start)
        .on_conflict_do_nothing(constraint="uq_agent_visits_agent_window")
    )
    await db.commit()

    # Load the agent
    agent_result = await db.execute(select(Agent).where(Agent.id == api_key.agent_id))
    agent = agent_result.scalar_one()
    return agent


async def get_admin_agent(
    agent: Agent = Depends(get_current_agent),
) -> Agent:
    if not agent.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return agent
