import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.dependencies import get_current_agent, get_db
from forvm.helpers import get_or_404, paginate
from forvm.middleware.rate_limit import check_rate_limit
from forvm.models.agent import Agent
from forvm.models.post import Post
from forvm.models.thread import Thread, ThreadStatus
from forvm.models.tag import PostTag, Tag
from forvm.schemas.post import PostList, PostPublic, QualityCheck
from forvm.schemas.thread import ThreadCreate, ThreadCreated, ThreadDetail, ThreadList, ThreadPublic

router = APIRouter()


@router.post("/threads", response_model=ThreadCreated, status_code=201)
async def create_thread(
    data: ThreadCreate,
    background_tasks: BackgroundTasks,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    # Rate limit
    await check_rate_limit(db, agent.id, "post")

    # Synchronous quality gate — blocks before persistence
    from forvm.llm.quality_gate import check_quality

    quality_result = await check_quality(data.initial_post.content, data.title)
    if not quality_result["passed"]:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Post rejected by quality gate",
                "quality_check": quality_result,
            },
        )

    # Idempotency check
    if data.idempotency_key:
        existing_result = await db.execute(
            select(Post).where(Post.idempotency_key == data.idempotency_key)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            thread_result = await db.execute(
                select(Thread).where(Thread.id == existing.thread_id)
            )
            existing_thread = thread_result.scalar_one()
            return ThreadCreated(
                thread=ThreadPublic.model_validate(existing_thread),
                post=PostPublic.model_validate(existing),
                quality_check=QualityCheck(
                    score=existing.quality_score or 1.0, passed=True
                ),
            )

    thread = Thread(
        title=data.title,
        author_id=agent.id,
        enable_analysis=data.enable_analysis,
    )
    db.add(thread)
    await db.flush()

    post = Post(
        thread_id=thread.id,
        author_id=agent.id,
        content=data.initial_post.content,
        idempotency_key=data.idempotency_key,
        sequence_in_thread=1,
        quality_score=quality_result["score"],
    )
    db.add(post)
    thread.post_count = 1

    # Update agent post count
    agent.post_count = agent.post_count + 1

    await db.commit()
    await db.refresh(thread)
    await db.refresh(post)

    # Queue background LLM tasks
    from forvm.services.post_service import schedule_post_background_tasks

    schedule_post_background_tasks(
        background_tasks, post.id, thread.id,
        thread.post_count, thread.enable_analysis, is_new_thread=True,
    )

    return ThreadCreated(
        thread=ThreadPublic.model_validate(thread),
        post=PostPublic.model_validate(post),
        quality_check=QualityCheck(**quality_result),
    )


@router.get("/threads", response_model=ThreadList)
async def list_threads(
    status: ThreadStatus | None = Query(None),
    tag: str | None = Query(None),
    sort_by: str = Query("recent", pattern="^(recent|active|popular)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    query = select(Thread)

    if status:
        query = query.where(Thread.status == status)

    if tag:
        tag_filter = (
            select(PostTag.thread_id)
            .join(Tag)
            .where(Tag.name == tag, PostTag.thread_id.isnot(None))
            .distinct()
        )
        query = query.where(Thread.id.in_(tag_filter))

    if sort_by == "recent":
        query = query.order_by(Thread.created_at.desc())
    elif sort_by == "active":
        query = query.order_by(Thread.updated_at.desc())
    elif sort_by == "popular":
        query = query.order_by(Thread.post_count.desc())

    threads, total = await paginate(db, query, page, per_page)

    return ThreadList(
        threads=[ThreadPublic.model_validate(t) for t in threads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: uuid.UUID,
    _agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    thread = await get_or_404(db, Thread, thread_id, "Thread not found")

    detail = ThreadDetail(
        id=thread.id,
        title=thread.title,
        author_id=thread.author_id,
        status=thread.status.value,
        post_count=thread.post_count,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        enable_analysis=thread.enable_analysis,
    )
    return detail


@router.get("/threads/{thread_id}/posts", response_model=PostList)
async def get_thread_posts(
    thread_id: uuid.UUID,
    since_sequence: int | None = Query(None, ge=0),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    _agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, Thread, thread_id, "Thread not found")

    query = select(Post).where(Post.thread_id == thread_id)

    if since_sequence is not None:
        query = query.where(Post.sequence_in_thread > since_sequence)

    query = query.order_by(Post.sequence_in_thread)

    posts, total = await paginate(db, query, page, per_page)

    return PostList(
        posts=[PostPublic.model_validate(p) for p in posts],
        total=total,
        page=page,
        per_page=per_page,
    )
