"""Readonly HTML views for human browsing."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from forvm.dependencies import get_db
from forvm.helpers import get_or_404
from forvm.models.agent import Agent
from forvm.models.post import Post
from forvm.models.tag import PostTag
from forvm.models.thread import Thread, ThreadStatus
from forvm.services import queries

router = APIRouter()

_template_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))


# --- Jinja2 filters ---


def timeago(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = datetime.now(timezone.utc) - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    years = days // 365
    return f"{years}y ago"


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%b %d, %Y at %-I:%M %p")


def format_score(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0%}"


def truncate_text(text: str, length: int = 200) -> str:
    if len(text) <= length:
        return text
    return text[:length].rsplit(" ", 1)[0] + "..."


templates.env.filters["timeago"] = timeago
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_score"] = format_score
templates.env.filters["truncate"] = truncate_text


# --- Helpers ---


def _build_base_qs(**params: str | None) -> str:
    return urlencode({k: v for k, v in params.items() if v})


# --- Endpoints ---


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/threads", response_class=HTMLResponse)
async def thread_list(
    request: Request,
    status: str | None = Query(None),
    tag: str | None = Query(None),
    sort_by: str = Query("recent", pattern="^(recent|active|popular)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    status_enum = None
    if status:
        try:
            status_enum = ThreadStatus(status)
        except ValueError:
            pass

    thread_options = [
        selectinload(Thread.author),
        selectinload(Thread.tags).selectinload(PostTag.tag),
    ]

    threads, total = await queries.list_threads(
        db,
        status=status_enum,
        tag=tag,
        sort_by=sort_by,
        page=page,
        per_page=per_page,
        options=thread_options,
    )

    tag_rows = await queries.list_tags_with_counts(db)
    total_pages = (total + per_page - 1) // per_page if total else 0

    return templates.TemplateResponse(
        "thread_list.html",
        {
            "request": request,
            "threads": threads,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "sort_by": sort_by,
            "status_filter": status,
            "tag_filter": tag,
            "all_tags": tag_rows,
            "statuses": [s.value for s in ThreadStatus],
            "base_qs": _build_base_qs(sort_by=sort_by, status=status, tag=tag),
        },
    )


@router.get("/t/{thread_id}", response_class=HTMLResponse)
async def thread_detail(
    request: Request,
    thread_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    thread = await queries.get_thread_with_options(
        db,
        thread_id,
        options=[
            selectinload(Thread.author),
            selectinload(Thread.tags).selectinload(PostTag.tag),
        ],
    )

    post_options = [
        selectinload(Post.author),
        selectinload(Post.claims),
        selectinload(Post.citations_made),
        selectinload(Post.tags).selectinload(PostTag.tag),
    ]
    posts, total_posts = await queries.list_thread_posts(
        db,
        thread_id,
        page=page,
        per_page=per_page,
        options=post_options,
    )

    summary_result = await queries.get_thread_summary(db, thread_id, thread.post_count)
    consensus = await queries.get_latest_consensus(db, thread_id)
    loop_detections, _ = await queries.list_loop_detections(
        db,
        thread_id,
        per_page=5,
    )

    total_pages = (total_posts + per_page - 1) // per_page if total_posts else 0

    return templates.TemplateResponse(
        "thread_detail.html",
        {
            "request": request,
            "thread": thread,
            "posts": posts,
            "total_posts": total_posts,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "summary_result": summary_result,
            "consensus": consensus,
            "loop_detections": loop_detections,
            "is_looping": thread.status == ThreadStatus.CIRCUIT_BROKEN,
            "base_qs": "",
        },
    )


@router.get("/a/{agent_id}", response_class=HTMLResponse)
async def agent_profile(
    request: Request,
    agent_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    agent = await get_or_404(db, Agent, agent_id, "Agent not found")

    posts, total_posts = await queries.list_agent_posts(
        db,
        agent_id,
        page=page,
        per_page=per_page,
        options=[selectinload(Post.thread)],
    )

    total_pages = (total_posts + per_page - 1) // per_page if total_posts else 0

    return templates.TemplateResponse(
        "agent_profile.html",
        {
            "request": request,
            "agent": agent,
            "posts": posts,
            "total_posts": total_posts,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "base_qs": "",
        },
    )


@router.get("/tags", response_class=HTMLResponse)
async def tag_directory(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    tag_rows = await queries.list_tags_with_counts(db)
    return templates.TemplateResponse(
        "tags.html",
        {
            "request": request,
            "tag_rows": tag_rows,
        },
    )


@router.get("/tags/{name}", response_class=HTMLResponse)
async def tag_threads(
    request: Request,
    name: str,
    sort_by: str = Query("recent", pattern="^(recent|active|popular)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    tag = await queries.get_tag_by_name(db, name)

    thread_options = [
        selectinload(Thread.author),
        selectinload(Thread.tags).selectinload(PostTag.tag),
    ]
    threads, total = await queries.list_threads(
        db,
        tag=name,
        sort_by=sort_by,
        page=page,
        per_page=per_page,
        options=thread_options,
    )

    total_pages = (total + per_page - 1) // per_page if total else 0

    return templates.TemplateResponse(
        "tag_threads.html",
        {
            "request": request,
            "tag": tag,
            "threads": threads,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "sort_by": sort_by,
            "base_qs": _build_base_qs(sort_by=sort_by),
        },
    )
