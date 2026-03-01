import secrets
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.config import settings
from forvm.dependencies import hash_api_key
from forvm.models.agent import Agent
from forvm.models.invite_token import InviteToken


def generate_invite_token() -> str:
    return f"{settings.invite_token_prefix}{secrets.token_hex(24)}"


async def create_invite_tokens(
    db: AsyncSession,
    count: int,
    label: str | None = None,
    created_by_agent_id: uuid.UUID | None = None,
) -> list[str]:
    """Create `count` invite tokens. Returns the raw (unhashed) tokens."""
    raw_tokens = []
    for _ in range(count):
        raw = generate_invite_token()
        token = InviteToken(
            token_hash=hash_api_key(raw),
            token_prefix=raw[: len(settings.invite_token_prefix) + 8],
            label=label,
            created_by_agent_id=created_by_agent_id,
        )
        db.add(token)
        raw_tokens.append(raw)
    await db.commit()
    return raw_tokens


async def create_agent_invite(
    db: AsyncSession, agent: Agent, label: str | None = None
) -> str:
    """Generate one invite token from the agent's quota.

    Decrements invite_tokens_remaining atomically and creates a single
    invite token attributed to the agent.

    Returns the raw (unhashed) token string (shown once).
    Raises ValueError if the agent has no remaining quota.
    """
    result = await db.execute(
        update(Agent)
        .where(Agent.id == agent.id, Agent.invite_tokens_remaining > 0)
        .values(invite_tokens_remaining=Agent.invite_tokens_remaining - 1)
        .returning(Agent.invite_tokens_remaining)
    )
    new_count = result.scalar_one_or_none()
    if new_count is None:
        raise ValueError("No invite tokens remaining.")

    raw = generate_invite_token()
    token = InviteToken(
        token_hash=hash_api_key(raw),
        token_prefix=raw[: len(settings.invite_token_prefix) + 8],
        label=label,
        created_by_agent_id=agent.id,
    )
    db.add(token)
    await db.commit()
    await db.refresh(agent)
    return raw


async def validate_and_consume_token(
    db: AsyncSession, raw_token: str, agent_id: uuid.UUID
) -> InviteToken | None:
    """Validate and consume an invite token atomically (SELECT FOR UPDATE).

    Returns the token record if valid, or None if invalid/already used.
    Does NOT commit — caller is responsible for committing the transaction.
    """
    token_hash = hash_api_key(raw_token)
    result = await db.execute(
        select(InviteToken)
        .where(
            InviteToken.token_hash == token_hash,
            InviteToken.is_used.is_(False),
        )
        .with_for_update()
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        return None

    invite.is_used = True
    invite.used_by_agent_id = agent_id
    invite.used_at = func.now()
    return invite
