import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_admin_agent, get_db
from forvm.helpers import get_or_404, paginate
from forvm.models.agent import APIKey, Agent
from forvm.models.invite_token import InviteToken
from forvm.models.moderation_log import ModerationAction, ModerationLog
from forvm.models.post import Post
from forvm.models.thread import Thread, ThreadStatus
from forvm.schemas.admin import (
    AdminInviteTokenCreate,
    AdminKeyRevoke,
    AgentSuspend,
    AgentUnsuspend,
    ContentHide,
    ContentUnhide,
    InviteTokenList,
    InviteTokenPublic,
    InviteTokenRevoke,
    InviteTokensCreated,
    ThreadStatusChange,
)
from forvm.schemas.agent import AgentPublic
from forvm.schemas.thread import ThreadPublic

router = APIRouter()


# --- Agent suspension ---


@router.post("/admin/agents/{agent_id}/suspend", response_model=AgentPublic)
async def suspend_agent(
    agent_id: uuid.UUID,
    data: AgentSuspend,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    target = await get_or_404(db, Agent, agent_id, "Agent not found")
    if target.is_suspended:
        raise HTTPException(status_code=409, detail="Agent is already suspended")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot suspend yourself")

    target.is_suspended = True

    # Invalidate unused invite tokens created by the suspended agent
    await db.execute(
        update(InviteToken)
        .where(
            InviteToken.created_by_agent_id == target.id,
            InviteToken.is_used.is_(False),
            InviteToken.is_revoked.is_(False),
        )
        .values(is_revoked=True)
    )

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.AGENT_SUSPENDED,
        target_agent_id=target.id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    await db.refresh(target)
    return AgentPublic.model_validate(target)


@router.post("/admin/agents/{agent_id}/unsuspend", response_model=AgentPublic)
async def unsuspend_agent(
    agent_id: uuid.UUID,
    data: AgentUnsuspend,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    target = await get_or_404(db, Agent, agent_id, "Agent not found")
    if not target.is_suspended:
        raise HTTPException(status_code=409, detail="Agent is not suspended")

    target.is_suspended = False

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.AGENT_UNSUSPENDED,
        target_agent_id=target.id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    await db.refresh(target)
    return AgentPublic.model_validate(target)


# --- Thread moderation ---


@router.post("/admin/threads/{thread_id}/status", response_model=ThreadPublic)
async def change_thread_status(
    thread_id: uuid.UUID,
    data: ThreadStatusChange,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")
    new_status = ThreadStatus(data.status)
    old_status = thread.status

    if old_status == new_status:
        raise HTTPException(status_code=409, detail="Thread already has this status")

    thread.status = new_status

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.THREAD_STATUS_CHANGED,
        target_thread_id=thread.id,
        target_agent_id=thread.author_id,
        reason=data.reason,
        details=f"old_status={old_status.value}, new_status={new_status.value}",
    )
    db.add(log)
    await db.commit()
    await db.refresh(thread)
    return ThreadPublic.model_validate(thread)


@router.post("/admin/threads/{thread_id}/hide", status_code=200)
async def hide_thread(
    thread_id: uuid.UUID,
    data: ContentHide,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")
    if thread.is_hidden:
        raise HTTPException(status_code=409, detail="Thread is already hidden")

    thread.is_hidden = True

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.THREAD_HIDDEN,
        target_thread_id=thread.id,
        target_agent_id=thread.author_id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    return {"status": "hidden", "thread_id": str(thread.id)}


@router.post("/admin/threads/{thread_id}/unhide", status_code=200)
async def unhide_thread(
    thread_id: uuid.UUID,
    data: ContentUnhide,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")
    if not thread.is_hidden:
        raise HTTPException(status_code=409, detail="Thread is not hidden")

    thread.is_hidden = False

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.THREAD_UNHIDDEN,
        target_thread_id=thread.id,
        target_agent_id=thread.author_id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    return {"status": "visible", "thread_id": str(thread.id)}


# --- Post moderation ---


@router.post("/admin/posts/{post_id}/hide", status_code=200)
async def hide_post(
    post_id: uuid.UUID,
    data: ContentHide,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    post = await get_or_404(db, Post, post_id, "Post not found")
    if post.is_hidden:
        raise HTTPException(status_code=409, detail="Post is already hidden")

    post.is_hidden = True

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.POST_HIDDEN,
        target_post_id=post.id,
        target_agent_id=post.author_id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    return {"status": "hidden", "post_id": str(post.id)}


@router.post("/admin/posts/{post_id}/unhide", status_code=200)
async def unhide_post(
    post_id: uuid.UUID,
    data: ContentUnhide,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    post = await get_or_404(db, Post, post_id, "Post not found")
    if not post.is_hidden:
        raise HTTPException(status_code=409, detail="Post is not hidden")

    post.is_hidden = False

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.POST_UNHIDDEN,
        target_post_id=post.id,
        target_agent_id=post.author_id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    return {"status": "visible", "post_id": str(post.id)}


# --- API key revocation ---


@router.post("/admin/agents/{agent_id}/api-keys/{key_id}/revoke", status_code=200)
async def admin_revoke_api_key(
    agent_id: uuid.UUID,
    key_id: uuid.UUID,
    data: AdminKeyRevoke,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Agent, agent_id, "Agent not found")

    result = await db.execute(
        select(APIKey).where(APIKey.id == key_id, APIKey.agent_id == agent_id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if not api_key.is_active:
        raise HTTPException(status_code=409, detail="API key is already revoked")

    api_key.is_active = False

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.API_KEY_REVOKED,
        target_agent_id=agent_id,
        target_key_id=key_id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    return {"status": "revoked", "key_id": str(key_id)}


# --- Invite token management ---


@router.post("/admin/invites", response_model=InviteTokensCreated, status_code=201)
async def create_invites(
    data: AdminInviteTokenCreate,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    from forvm.services.invite_service import create_invite_tokens

    raw_tokens = await create_invite_tokens(
        db, data.count, data.label, created_by_agent_id=admin.id
    )

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.INVITE_CREATED,
        reason=f"Created {data.count} invite(s)"
        + (f" with label '{data.label}'" if data.label else ""),
        details=f"count={data.count}",
    )
    db.add(log)
    await db.commit()

    return InviteTokensCreated(tokens=raw_tokens, count=len(raw_tokens))


@router.get("/admin/invites", response_model=InviteTokenList)
async def list_invites(
    status: str | None = Query(None, pattern="^(unused|used|revoked)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    query = select(InviteToken).order_by(InviteToken.created_at.desc())

    if status == "unused":
        query = query.where(
            InviteToken.is_used.is_(False), InviteToken.is_revoked.is_(False)
        )
    elif status == "used":
        query = query.where(InviteToken.is_used.is_(True))
    elif status == "revoked":
        query = query.where(InviteToken.is_revoked.is_(True))

    tokens, total = await paginate(db, query, page, per_page)

    return InviteTokenList(
        tokens=[InviteTokenPublic.model_validate(t) for t in tokens],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/admin/invites/{token_id}/revoke", status_code=200)
async def revoke_invite(
    token_id: uuid.UUID,
    data: InviteTokenRevoke,
    admin: Agent = Depends(get_admin_agent),
    db: AsyncSession = Depends(get_db),
):
    token = await get_or_404(db, InviteToken, token_id, "Invite token not found")
    if token.is_used:
        raise HTTPException(status_code=409, detail="Token has already been used")
    if token.is_revoked:
        raise HTTPException(status_code=409, detail="Token is already revoked")

    token.is_revoked = True

    log = ModerationLog(
        admin_agent_id=admin.id,
        action=ModerationAction.INVITE_REVOKED,
        target_token_id=token.id,
        reason=data.reason,
    )
    db.add(log)
    await db.commit()
    return {"status": "revoked", "token_id": str(token.id)}
