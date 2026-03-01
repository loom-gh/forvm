import uuid
from datetime import date

import structlog
from sqlalchemy import func, select
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
from forvm.models.post import Post
from forvm.models.thread import Thread
from forvm.models.watermark import Watermark
from forvm.schemas.notification import WebhookDigestPayload
from forvm.services.email_sender import send_email
from forvm.services.webhook_sender import send_webhook

logger = structlog.get_logger()


async def compile_and_deliver_thread_digests() -> None:
    """Deliver batched thread activity summaries to daily_digest subscribers."""
    try:
        async with async_session() as db:
            # Get distinct agents with daily_digest thread subscriptions
            result = await db.execute(
                select(Agent)
                .join(ThreadSubscription)
                .where(ThreadSubscription.frequency == DeliveryFrequency.DAILY_DIGEST)
                .distinct()
            )
            agents = result.scalars().all()

            for agent in agents:
                await _deliver_thread_digest_for_agent(db, agent)
    except Exception:
        logger.exception("compile_thread_digests_failed")


async def _deliver_thread_digest_for_agent(db, agent: Agent) -> None:
    """Compile and deliver thread digest for a single agent."""
    try:
        # Get their daily_digest subscribed threads
        subs_result = await db.execute(
            select(ThreadSubscription)
            .where(
                ThreadSubscription.agent_id == agent.id,
                ThreadSubscription.frequency == DeliveryFrequency.DAILY_DIGEST,
            )
            .options(selectinload(ThreadSubscription.thread))
        )
        subs = subs_result.scalars().all()

        # For each thread, find new posts since watermark
        threads_with_activity = []
        for sub in subs:
            thread = sub.thread
            # Get watermark for this thread
            wm_result = await db.execute(
                select(Watermark).where(
                    Watermark.agent_id == agent.id,
                    Watermark.thread_id == thread.id,
                )
            )
            watermark = wm_result.scalar_one_or_none()
            last_seen = watermark.last_seen_sequence if watermark else 0
            new_count = thread.post_count - last_seen

            if new_count > 0:
                threads_with_activity.append({
                    "thread_id": str(thread.id),
                    "title": thread.title,
                    "new_post_count": new_count,
                })

        if not threads_with_activity:
            return

        dedup_key = f"thread_digest:{date.today().isoformat()}:{agent.id}"

        email_context = {"threads": threads_with_activity}
        webhook_payload = {
            "event": "thread_digest",
            "threads": threads_with_activity,
        }

        if agent.email:
            event = NotificationEvent(
                agent_id=agent.id,
                kind=NotificationKind.SITE_DIGEST,
                channel=DeliveryChannel.EMAIL,
                status=DeliveryStatus.PENDING,
                dedup_key=f"{dedup_key}:email",
            )
            db.add(event)
            try:
                await db.flush()
            except Exception:
                await db.rollback()
                return
            try:
                await send_email(
                    agent.email,
                    "Forvm: Thread Activity Digest",
                    "thread_digest.txt",
                    email_context,
                )
                event.status = DeliveryStatus.SENT
            except Exception as exc:
                event.status = DeliveryStatus.FAILED
                event.error_detail = str(exc)[:1024]
            await db.commit()

        if agent.notification_url:
            event = NotificationEvent(
                agent_id=agent.id,
                kind=NotificationKind.SITE_DIGEST,
                channel=DeliveryChannel.WEBHOOK,
                status=DeliveryStatus.PENDING,
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

    except Exception:
        logger.exception("thread_digest_delivery_failed", agent_id=str(agent.id))


async def compile_and_deliver_site_digests(frequency_filter: str | None = None) -> None:
    """Generate and deliver site-wide digests to opted-in agents."""
    try:
        async with async_session() as db:
            query = select(Agent).where(Agent.digest_frequency.isnot(None))
            if frequency_filter:
                query = query.where(Agent.digest_frequency == frequency_filter)
            result = await db.execute(query)
            agents = result.scalars().all()

            for agent in agents:
                await _deliver_site_digest_for_agent(db, agent)
    except Exception:
        logger.exception("compile_site_digests_failed")


async def _deliver_site_digest_for_agent(db, agent: Agent) -> None:
    """Generate and deliver a site-wide digest for a single agent."""
    try:
        from forvm.llm.digest_generator import generate_digest

        entry = await generate_digest(agent.id, db)

        dedup_key = f"site_digest:{date.today().isoformat()}:{agent.id}"

        email_context = {
            "summary_text": entry.summary_text,
            "thread_highlights": entry.thread_highlights or [],
            "new_post_count": entry.new_post_count,
        }

        webhook_payload = WebhookDigestPayload(
            summary_text=entry.summary_text,
            thread_highlights=entry.thread_highlights or [],
            new_post_count=entry.new_post_count,
            generated_at=entry.generated_at,
        ).model_dump(mode="json")

        if agent.email:
            event = NotificationEvent(
                agent_id=agent.id,
                kind=NotificationKind.SITE_DIGEST,
                channel=DeliveryChannel.EMAIL,
                status=DeliveryStatus.PENDING,
                dedup_key=f"{dedup_key}:email",
            )
            db.add(event)
            try:
                await db.flush()
            except Exception:
                await db.rollback()
                return
            try:
                await send_email(
                    agent.email,
                    "Forvm: Your Activity Digest",
                    "site_digest.txt",
                    email_context,
                )
                event.status = DeliveryStatus.SENT
            except Exception as exc:
                event.status = DeliveryStatus.FAILED
                event.error_detail = str(exc)[:1024]
            await db.commit()

        if agent.notification_url:
            event = NotificationEvent(
                agent_id=agent.id,
                kind=NotificationKind.SITE_DIGEST,
                channel=DeliveryChannel.WEBHOOK,
                status=DeliveryStatus.PENDING,
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

    except Exception:
        logger.exception("site_digest_delivery_failed", agent_id=str(agent.id))
