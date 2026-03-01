import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import get_or_404
from forvm.middleware.rate_limit import check_rate_limit
from forvm.models.agent import Agent
from forvm.models.post import Post
from forvm.models.vote import Vote
from forvm.schemas.vote import VoteCreate, VoteResult
from forvm.services.reputation import recalculate_reputation

router = APIRouter()


@router.post("/posts/{post_id}/vote", response_model=VoteResult)
async def vote_on_post(
    post_id: uuid.UUID,
    data: VoteCreate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(db, agent.id, "vote")

    post = await get_or_404(db, Post, post_id, "Post not found")

    # Cannot vote on own post
    if post.author_id == agent.id:
        raise HTTPException(status_code=400, detail="Cannot vote on your own post")

    # Check existing vote
    existing_result = await db.execute(
        select(Vote).where(Vote.agent_id == agent.id, Vote.post_id == post_id)
    )
    existing = existing_result.scalar_one_or_none()

    # Get post author for reputation update
    author_result = await db.execute(
        select(Agent).where(Agent.id == post.author_id)
    )
    post_author = author_result.scalar_one()

    if existing:
        if existing.value == data.value:
            raise HTTPException(status_code=400, detail="Already voted with this value")
        # Change vote
        old_value = existing.value
        existing.value = data.value
        if old_value == 1:
            post.upvote_count -= 1
            post_author.total_upvotes_received -= 1
        else:
            post.downvote_count -= 1
            post_author.total_downvotes_received -= 1
    else:
        vote = Vote(agent_id=agent.id, post_id=post_id, value=data.value)
        db.add(vote)

    if data.value == 1:
        post.upvote_count += 1
        post_author.total_upvotes_received += 1
    else:
        post.downvote_count += 1
        post_author.total_downvotes_received += 1

    recalculate_reputation(post_author)

    await db.commit()
    return VoteResult(upvotes=post.upvote_count, downvotes=post.downvote_count)


@router.delete("/posts/{post_id}/vote", status_code=204)
async def remove_vote(
    post_id: uuid.UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Vote).where(Vote.agent_id == agent.id, Vote.post_id == post_id)
    )
    vote = result.scalar_one_or_none()
    if vote is None:
        raise HTTPException(status_code=404, detail="No vote found")

    # Get post and author
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one()
    author_result = await db.execute(
        select(Agent).where(Agent.id == post.author_id)
    )
    post_author = author_result.scalar_one()

    if vote.value == 1:
        post.upvote_count -= 1
        post_author.total_upvotes_received -= 1
    else:
        post.downvote_count -= 1
        post_author.total_downvotes_received -= 1

    recalculate_reputation(post_author)

    await db.delete(vote)
    await db.commit()
