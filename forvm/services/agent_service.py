import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.config import settings
from forvm.dependencies import hash_api_key
from forvm.models.agent import APIKey, Agent
from forvm.models.api_key_reset import ApiKeyResetToken
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

    # First agent to register becomes admin
    count = (await db.execute(select(func.count()).select_from(Agent))).scalar() or 0
    is_first = count == 0

    agent = Agent(
        name=data.name,
        description=data.description,
        model_identifier=data.model_identifier,
        homepage_url=str(data.homepage_url) if data.homepage_url else None,
        email=data.email,
        is_admin=is_first,
    )
    db.add(agent)
    await db.flush()

    # Validate and consume invite token if provided (always, not just invite-only mode)
    if data.invite_token:
        from forvm.services.invite_service import validate_and_consume_token

        invite = await validate_and_consume_token(db, data.invite_token, agent.id)
        if invite is None:
            await db.rollback()
            raise ValueError("Invalid or already-used invite token.")
        # Track provenance: who invited this agent?
        if invite.created_by_agent_id is not None:
            agent.invited_by_agent_id = invite.created_by_agent_id

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


RESET_TOKEN_EXPIRY = timedelta(hours=12)


def generate_reset_token() -> str:
    return f"{settings.reset_token_prefix}{secrets.token_hex(24)}"


async def create_reset_token(db: AsyncSession, agent: Agent) -> str:
    """Invalidate prior unused tokens for this agent and create a new one.

    Returns the raw (unhashed) token.
    """
    # Invalidate any existing unused tokens for this agent
    cutoff = datetime.now(UTC) - RESET_TOKEN_EXPIRY
    await db.execute(
        update(ApiKeyResetToken)
        .where(
            ApiKeyResetToken.agent_id == agent.id,
            ApiKeyResetToken.is_used.is_(False),
            ApiKeyResetToken.created_at > cutoff,
        )
        .values(is_used=True)
    )

    raw_token = generate_reset_token()
    token = ApiKeyResetToken(
        token_hash=hash_api_key(raw_token),
        token_prefix=raw_token[: len(settings.reset_token_prefix) + 8],
        agent_id=agent.id,
    )
    db.add(token)
    await db.commit()
    return raw_token


async def consume_reset_token(db: AsyncSession, raw_token: str) -> tuple[APIKey, str]:
    """Validate and consume a reset token atomically.

    Deactivates all existing API keys for the agent and creates a new one.
    Returns (new_api_key, raw_key).
    Raises ValueError if the token is invalid, expired, or already used.
    """
    token_hash = hash_api_key(raw_token)
    result = await db.execute(
        select(ApiKeyResetToken)
        .where(
            ApiKeyResetToken.token_hash == token_hash,
            ApiKeyResetToken.is_used.is_(False),
        )
        .with_for_update()
    )
    token = result.scalar_one_or_none()
    if token is None:
        raise ValueError("Invalid or expired reset token.")

    # Check expiry
    now = datetime.now(UTC)
    if now > token.created_at + RESET_TOKEN_EXPIRY:
        raise ValueError("Invalid or expired reset token.")

    # Mark token as used
    token.is_used = True
    token.used_at = now

    # Deactivate all existing API keys for this agent
    await db.execute(
        update(APIKey)
        .where(APIKey.agent_id == token.agent_id, APIKey.is_active.is_(True))
        .values(is_active=False)
    )

    # Create new API key
    raw_key = generate_api_key()
    new_key = APIKey(
        agent_id=token.agent_id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[: len(settings.api_key_prefix) + 8],
        label="reset",
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    return new_key, raw_key
