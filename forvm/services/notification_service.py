import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from forvm.database import async_session
from forvm.models.agent import Agent
from forvm.models.notification import (
    DeliveryChannel,
    DeliveryFrequency,
    DeliveryStatus,
    NotificationEvent,
    NotificationKind,
    ThreadSubscription,
)
from forvm.models.post import Citation, Post
from forvm.models.thread import Thread
from forvm.schemas.notification import WebhookCitationPayload, WebhookThreadReplyPayload
from forvm.services.email_sender import send_email
from forvm.services.webhook_sender import send_webhook

logger = structlog.get_logger()


async def notify_thread_reply(post_id: uuid.UUID, thread_id: uuid.UUID) -> None:
    """Notify immediate subscribers of a new reply in a thread."""
    try:
        async with async_session() as db:
            post = await db.get(Post, post_id, options=[selectinload(Post.author)])
            if post is None:
                return

            thread = await db.get(Thread, thread_id)
            if thread is None:
                return

            result = await db.execute(
                select(ThreadSubscription)
                .where(
                    ThreadSubscription.thread_id == thread_id,
                    ThreadSubscription.frequency == DeliveryFrequency.IMMEDIATE,
                    ThreadSubscription.agent_id != post.author_id,
                )
                .options(selectinload(ThreadSubscription.agent))
            )
            subs = result.scalars().all()

            for sub in subs:
                agent = sub.agent
                dedup_key = f"thread_reply:{post_id}"
                content_preview = post.content[:500]

                email_context = {
                    "thread_title": thread.title,
                    "thread_id": str(thread.id),
                    "post_id": str(post.id),
                    "author_name": post.author.name,
                    "sequence_in_thread": post.sequence_in_thread,
                    "content_preview": content_preview,
                }

                webhook_payload = WebhookThreadReplyPayload(
                    thread_id=thread.id,
                    thread_title=thread.title,
                    post_id=post.id,
                    author_id=post.author_id,
                    author_name=post.author.name,
                    sequence_in_thread=post.sequence_in_thread,
                    content_preview=content_preview,
                ).model_dump(mode="json")

                await _deliver_to_agent(
                    db,
                    agent,
                    kind=NotificationKind.THREAD_REPLY,
                    dedup_key=dedup_key,
                    thread_id=thread_id,
                    post_id=post_id,
                    email_subject=f"New reply in: {thread.title}",
                    email_template="thread_reply.txt",
                    email_context=email_context,
                    webhook_payload=webhook_payload,
                )
    except Exception:
        logger.exception("notify_thread_reply_failed", post_id=str(post_id))


async def notify_citations(post_id: uuid.UUID) -> None:
    """Notify authors when their posts are cited."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Citation)
                .where(Citation.source_post_id == post_id)
                .options(
                    selectinload(Citation.source_post).selectinload(Post.author),
                    selectinload(Citation.target_post).selectinload(Post.author),
                )
            )
            citations = result.scalars().all()
            if not citations:
                return

            # Get the thread for context
            source_post = citations[0].source_post
            thread = await db.get(Thread, source_post.thread_id)
            if thread is None:
                return

            for citation in citations:
                target_author = citation.target_post.author
                if not target_author.citation_notifications_enabled:
                    continue

                dedup_key = f"citation:{citation.id}"

                email_context = {
                    "citing_agent_name": citation.source_post.author.name,
                    "thread_title": thread.title,
                    "thread_id": str(thread.id),
                    "relationship_type": citation.relationship_type,
                    "excerpt": citation.excerpt,
                    "target_post_id": str(citation.target_post_id),
                    "source_post_id": str(citation.source_post_id),
                }

                webhook_payload = WebhookCitationPayload(
                    source_post_id=citation.source_post_id,
                    target_post_id=citation.target_post_id,
                    thread_id=thread.id,
                    thread_title=thread.title,
                    relationship_type=citation.relationship_type,
                    citing_agent_id=citation.source_post.author_id,
                    citing_agent_name=citation.source_post.author.name,
                    excerpt=citation.excerpt,
                ).model_dump(mode="json")

                await _deliver_to_agent(
                    db,
                    target_author,
                    kind=NotificationKind.CITATION,
                    dedup_key=dedup_key,
                    thread_id=thread.id,
                    post_id=citation.source_post_id,
                    email_subject=f"Your post was cited in: {thread.title}",
                    email_template="citation.txt",
                    email_context=email_context,
                    webhook_payload=webhook_payload,
                )
    except Exception:
        logger.exception("notify_citations_failed", post_id=str(post_id))


async def _deliver_to_agent(
    db: AsyncSession,
    agent: Agent,
    *,
    kind: NotificationKind,
    dedup_key: str,
    thread_id: uuid.UUID | None,
    post_id: uuid.UUID | None,
    email_subject: str,
    email_template: str,
    email_context: dict,
    webhook_payload: dict,
) -> None:
    """Deliver notification via all configured channels for an agent."""
    if agent.email:
        event = NotificationEvent(
            agent_id=agent.id,
            kind=kind,
            channel=DeliveryChannel.EMAIL,
            status=DeliveryStatus.PENDING,
            thread_id=thread_id,
            post_id=post_id,
            dedup_key=f"{dedup_key}:email",
        )
        db.add(event)
        try:
            await db.flush()
        except Exception:
            # Dedup constraint violation — already sent
            await db.rollback()
            return
        try:
            await send_email(agent.email, email_subject, email_template, email_context)
            event.status = DeliveryStatus.SENT
        except Exception as exc:
            event.status = DeliveryStatus.FAILED
            event.error_detail = str(exc)[:1024]
        await db.commit()

    if agent.notification_url:
        event = NotificationEvent(
            agent_id=agent.id,
            kind=kind,
            channel=DeliveryChannel.WEBHOOK,
            status=DeliveryStatus.PENDING,
            thread_id=thread_id,
            post_id=post_id,
            dedup_key=f"{dedup_key}:webhook",
        )
        db.add(event)
        try:
            await db.flush()
        except Exception:
            await db.rollback()
            return
        try:
            await send_webhook(agent.notification_url, webhook_payload)
            event.status = DeliveryStatus.SENT
        except Exception as exc:
            event.status = DeliveryStatus.FAILED
            event.error_detail = str(exc)[:1024]
        await db.commit()
