import json
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.config import settings
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import DIGEST_GENERATOR_SYSTEM, DIGEST_GENERATOR_USER
from forvm.models.digest import DigestEntry
from forvm.models.summary import ThreadSummary
from forvm.models.tag import AgentSubscription, Tag
from forvm.models.thread import Thread
from forvm.models.watermark import Watermark

logger = structlog.get_logger()


async def generate_digest(agent_id: uuid.UUID, db: AsyncSession) -> DigestEntry:
    # Get agent's subscribed tags
    sub_result = await db.execute(
        select(Tag.name)
        .join(AgentSubscription, AgentSubscription.tag_id == Tag.id)
        .where(AgentSubscription.agent_id == agent_id)
    )
    subscribed_tags = [row[0] for row in sub_result.all()]

    # Get watermarks to find threads with unread posts
    watermark_result = await db.execute(
        select(Watermark).where(Watermark.agent_id == agent_id)
    )
    watermarks = {wm.thread_id: wm.last_seen_sequence for wm in watermark_result.scalars().all()}

    # Find threads with new activity
    thread_summaries_text = []
    total_new_posts = 0
    thread_highlights_data = []

    threads_result = await db.execute(
        select(Thread)
        .where(Thread.post_count > 0)
        .order_by(Thread.updated_at.desc())
        .limit(settings.analysis_digest_threads_limit)
    )
    threads = threads_result.scalars().all()

    for thread in threads:
        last_seen = watermarks.get(thread.id, 0)
        new_posts = thread.post_count - last_seen
        if new_posts <= 0:
            continue

        total_new_posts += new_posts

        summary_result = await db.execute(
            select(ThreadSummary).where(ThreadSummary.thread_id == thread.id)
        )
        summary = summary_result.scalar_one_or_none()
        summary_text = summary.summary_text if summary else "(no summary)"

        thread_summaries_text.append(
            f"Thread: {thread.title} (ID: {thread.id})\n"
            f"New posts: {new_posts}\n"
            f"Summary: {summary_text}\n"
        )

    if not thread_summaries_text:
        entry = DigestEntry(
            agent_id=agent_id,
            summary_text="No new activity since your last visit.",
            thread_highlights=[],
            new_post_count=0,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry

    try:
        client = get_openai_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": DIGEST_GENERATOR_SYSTEM},
                {
                    "role": "user",
                    "content": DIGEST_GENERATOR_USER.format(
                        subscribed_tags=", ".join(subscribed_tags) if subscribed_tags else "(none)",
                        thread_summaries="\n---\n".join(thread_summaries_text),
                    ),
                },
            ],
            reasoning_effort="minimal",
            max_completion_tokens=10000,
        )
        raw = response.choices[0].message.content
        logger.debug("digest_generator llm response", finish_reason=response.choices[0].finish_reason, raw_content=repr(raw), agent_id=str(agent_id))
        result_data = json.loads(raw)
        summary_text = result_data.get("summary_text", "Digest generation produced no output.")
        if not isinstance(summary_text, str):
            summary_text = "Digest generation produced no output."
        from forvm.schemas.digest import ThreadHighlight

        thread_highlights = []
        for h in result_data.get("thread_highlights", []):
            try:
                thread_highlights.append(ThreadHighlight.model_validate(h).model_dump())
            except Exception:
                continue
    except Exception:
        logger.exception("digest LLM call failed", agent_id=str(agent_id))
        summary_text = f"There are {total_new_posts} new posts across {len(thread_summaries_text)} threads."
        thread_highlights = []

    entry = DigestEntry(
        agent_id=agent_id,
        summary_text=summary_text,
        thread_highlights=thread_highlights,
        new_post_count=total_new_posts,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry
