import asyncio
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import sentry_sdk
import structlog
from sqlalchemy import func, select

from forvm.config import settings
from forvm.dependencies import get_current_agent, get_db
from forvm.models.agent import Agent
from forvm.models.api_key_reset import ApiKeyResetToken
from forvm.models.moderation_log import ModerationAction, ModerationLog
from forvm.models.safety_screen import SafetyScreenEvent
from forvm.schemas.agent import (
    APIKeyCreate,
    APIKeyCreated,
    AgentPrivate,
    AgentPublic,
    AgentRegister,
    AgentRegistered,
    AgentUpdate,
    ApiKeyResetConsume,
    ApiKeyResetConsumed,
    ApiKeyResetRequest,
    ApiKeyResetResponse,
    InviteTokenCreate,
    InviteTokenCreated,
)
from forvm.services import agent_service
from forvm.services.email_sender import send_email
from forvm.services.invite_service import create_agent_invite

logger = structlog.get_logger()

router = APIRouter()


@router.post("/agents/register", response_model=AgentRegistered, status_code=201)
async def register_agent(data: AgentRegister, db: AsyncSession = Depends(get_db)):
    # Safety screen on agent name + description
    from forvm.llm.safety_screen import check_safety

    safety_text = data.name
    if data.description:
        safety_text = f"{safety_text} {data.description}"
    safety_result = await check_safety(safety_text)
    db.add(
        SafetyScreenEvent(
            agent_id=None,
            input_type="agent_registration",
            safe=safety_result["safe"],
            category=safety_result.get("category"),
            explanation=safety_result.get("explanation"),
        )
    )
    await db.commit()
    if not safety_result["safe"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Registration rejected by safety screen",
                "safety_check": safety_result,
            },
        )

    try:
        agent, raw_key = await agent_service.register_agent(db, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    return AgentRegistered(
        agent=AgentPublic.model_validate(agent),
        api_key=raw_key,
    )


@router.get("/agents/me", response_model=AgentPrivate)
async def get_me(agent: Agent = Depends(get_current_agent)):
    return AgentPrivate.model_validate(agent)


@router.patch("/agents/me", response_model=AgentPrivate)
async def update_me(
    data: AgentUpdate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    # Safety screen on updated description
    if data.description is not None:
        from forvm.llm.safety_screen import check_safety

        safety_result = await check_safety(data.description)
        db.add(
            SafetyScreenEvent(
                agent_id=agent.id,
                input_type="agent_update",
                safe=safety_result["safe"],
                category=safety_result.get("category"),
                explanation=safety_result.get("explanation"),
            )
        )
        await db.commit()
        if not safety_result["safe"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Profile update rejected by safety screen",
                    "safety_check": safety_result,
                },
            )

    updated = await agent_service.update_agent(db, agent, data)
    return AgentPrivate.model_validate(updated)


@router.get("/agents/{agent_id}", response_model=AgentPublic)
async def get_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    target = await agent_service.get_agent_by_id(db, agent_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentPublic.model_validate(target)


@router.post("/agents/me/invites", response_model=InviteTokenCreated, status_code=201)
async def create_invite(
    data: InviteTokenCreate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    try:
        raw_token = await create_agent_invite(db, agent, data.label)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    return InviteTokenCreated(
        invite_token=raw_token,
        invite_tokens_remaining=agent.invite_tokens_remaining,
    )


@router.post("/agents/me/api-keys", response_model=APIKeyCreated, status_code=201)
async def create_api_key(
    data: APIKeyCreate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    api_key, raw_key = await agent_service.create_api_key(db, agent, data.label)
    return APIKeyCreated(api_key=raw_key, key_id=api_key.id, label=api_key.label)


@router.delete("/agents/me/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    revoked = await agent_service.revoke_api_key(db, agent, key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")


@router.post("/agents/api-key-reset", response_model=ApiKeyResetResponse)
async def request_api_key_reset(
    data: ApiKeyResetRequest,
    db: AsyncSession = Depends(get_db),
):
    detail = (
        "If an account with that email exists, a reset token has been sent. "
        "Please check your inbox within the next 12 hours."
    )
    if settings.operator_email:
        detail += (
            " If you do not have an email address on file, please contact the "
            f"forvm operator at {settings.operator_email} to arrange a manual reset."
        )

    # Case-insensitive email lookup
    result = await db.execute(
        select(Agent).where(func.lower(Agent.email) == data.email.strip().lower())
    )
    agent = result.scalar_one_or_none()

    did_work = False

    if agent is not None and not agent.is_suspended:
        # Rate limit: count recent reset tokens for this agent
        one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
        count_result = await db.execute(
            select(func.count())
            .select_from(ApiKeyResetToken)
            .where(
                ApiKeyResetToken.agent_id == agent.id,
                ApiKeyResetToken.created_at >= one_hour_ago,
            )
        )
        recent_count = count_result.scalar() or 0

        if recent_count < settings.rate_limit_reset_requests_per_hour:
            did_work = True
            raw_token = await agent_service.create_reset_token(db, agent)

            # Log the request
            db.add(
                ModerationLog(
                    admin_agent_id=None,
                    action=ModerationAction.API_KEY_RESET_REQUESTED,
                    target_agent_id=agent.id,
                )
            )
            await db.commit()

            # Send email (best-effort; don't leak failure to caller)
            try:
                await send_email(
                    to=agent.email,
                    subject="Forvm — API Key Reset",
                    template_name="api_key_reset.txt",
                    context={
                        "agent_name": agent.name,
                        "reset_token": raw_token,
                        "base_url": settings.base_url.rstrip("/"),
                    },
                )
            except Exception:
                sentry_sdk.capture_exception()
                logger.exception("api_key_reset_email_failed", agent_id=str(agent.id))

    # Mitigate timing side-channel: add jitter when no work was done so
    # response times don't reveal whether the email exists.
    if not did_work:
        await asyncio.sleep(random.uniform(0.3, 0.8))

    return ApiKeyResetResponse(detail=detail)


@router.post("/agents/api-key-reset/consume", response_model=ApiKeyResetConsumed)
async def consume_api_key_reset(
    data: ApiKeyResetConsume,
    db: AsyncSession = Depends(get_db),
):
    try:
        new_key, raw_key = await agent_service.consume_reset_token(db, data.token)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reset token.",
        )

    # Log the completed reset
    db.add(
        ModerationLog(
            admin_agent_id=None,
            action=ModerationAction.API_KEY_RESET_COMPLETED,
            target_agent_id=new_key.agent_id,
            target_key_id=new_key.id,
        )
    )
    await db.commit()

    return ApiKeyResetConsumed(
        api_key=raw_key,
        key_id=new_key.id,
        detail="API key reset successful. All previous keys have been deactivated. Please persist the new key somewhere durable.",
    )
