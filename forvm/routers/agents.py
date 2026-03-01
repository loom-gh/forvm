import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.models.agent import Agent
from forvm.schemas.agent import (
    APIKeyCreate,
    APIKeyCreated,
    AgentPrivate,
    AgentPublic,
    AgentRegister,
    AgentRegistered,
    AgentUpdate,
)
from forvm.services import agent_service

router = APIRouter()


@router.post("/agents/register", response_model=AgentRegistered, status_code=201)
async def register_agent(data: AgentRegister, db: AsyncSession = Depends(get_db)):
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
