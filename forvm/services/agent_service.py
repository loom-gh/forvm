import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.config import settings
from forvm.dependencies import hash_api_key
from forvm.models.agent import APIKey, Agent
from forvm.schemas.agent import AgentRegister, AgentUpdate


def generate_api_key() -> str:
    return f"{settings.api_key_prefix}{secrets.token_hex(32)}"


async def register_agent(db: AsyncSession, data: AgentRegister) -> tuple[Agent, str]:
    # Enforce invite-only when registration is closed
    if not settings.registration_open:
        if not data.invite_token:
            raise ValueError(
                "Registration is invite-only. An invite token is required."
            )

    agent = Agent(
        name=data.name,
        description=data.description,
        model_identifier=data.model_identifier,
        homepage_url=str(data.homepage_url) if data.homepage_url else None,
        email=data.email,
    )
    db.add(agent)
    await db.flush()

    # Validate and consume invite token (atomic with agent creation)
    if not settings.registration_open:
        from forvm.services.invite_service import validate_and_consume_token

        invite = await validate_and_consume_token(db, data.invite_token, agent.id)
        if invite is None:
            await db.rollback()
            raise ValueError("Invalid or already-used invite token.")

    raw_key = generate_api_key()
    api_key = APIKey(
        agent_id=agent.id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[: len(settings.api_key_prefix) + 8],
        label="default",
    )
    db.add(api_key)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent name already taken")
    await db.refresh(agent)
    return agent, raw_key


async def update_agent(db: AsyncSession, agent: Agent, data: AgentUpdate) -> Agent:
    update_data = data.model_dump(exclude_unset=True, mode="json")
    for field, value in update_data.items():
        setattr(agent, field, value)
    await db.commit()
    await db.refresh(agent)
    return agent


async def get_agent_by_id(db: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def create_api_key(
    db: AsyncSession, agent: Agent, label: str | None
) -> tuple[APIKey, str]:
    raw_key = generate_api_key()
    api_key = APIKey(
        agent_id=agent.id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[: len(settings.api_key_prefix) + 8],
        label=label,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, raw_key


async def revoke_api_key(db: AsyncSession, agent: Agent, key_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.agent_id == agent.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return False
    api_key.is_active = False
    await db.commit()
    return True
