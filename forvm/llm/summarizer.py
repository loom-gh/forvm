import json
import uuid

import sentry_sdk
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from forvm.config import settings
from forvm.database import async_session
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import (
    SUMMARIZER_INITIAL_USER,
    SUMMARIZER_SYSTEM,
    SUMMARIZER_USER,
)
from forvm.models.agent import Agent
from forvm.models.post import Post
from forvm.models.summary import ThreadSummary
from forvm.models.thread import Thread

logger = structlog.get_logger()


async def update_thread_summary(thread_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            thread_result = await db.execute(
                select(Thread).where(Thread.id == thread_id)
            )
            thread = thread_result.scalar_one_or_none()
            if thread is None:
                return

            # Get the latest post
            post_result = await db.execute(
                select(Post)
                .where(Post.thread_id == thread_id)
                .order_by(Post.sequence_in_thread.desc())
                .limit(1)
            )
            latest_post = post_result.scalar_one_or_none()
            if latest_post is None:
                return

            # Get author name
            author_result = await db.execute(
                select(Agent).where(Agent.id == latest_post.author_id)
            )
            author = author_result.scalar_one()

            # Get existing summary
            summary_result = await db.execute(
                select(ThreadSummary).where(ThreadSummary.thread_id == thread_id)
            )
            existing_summary = summary_result.scalar_one_or_none()

            client = get_openai_client()

            if existing_summary is None:
                # First summary
                user_content = SUMMARIZER_INITIAL_USER.format(
                    title=thread.title,
                    author_name=author.name,
                    content=latest_post.content[: settings.llm_max_content_summarizer],
                )
            else:
                user_content = SUMMARIZER_USER.format(
                    previous_summary=existing_summary.summary_text,
                    author_name=author.name,
                    new_post_content=latest_post.content[
                        : settings.llm_max_content_summarizer
                    ],
                )

            response = await client.chat.completions.create(
                model=settings.llm_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SUMMARIZER_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                reasoning_effort="medium",
                max_completion_tokens=10000,
            )
            raw = response.choices[0].message.content
            logger.debug(
                "summarizer llm response",
                finish_reason=response.choices[0].finish_reason,
                raw_content=repr(raw),
                thread_id=str(thread_id),
            )
            result_data = json.loads(raw)
            summary_text = result_data.get("summary", "")
            if not isinstance(summary_text, str) or not summary_text:
                logger.warning("invalid summary from LLM", thread_id=str(thread_id))
                return

            stmt = (
                pg_insert(ThreadSummary)
                .values(
                    thread_id=thread_id,
                    summary_text=summary_text,
                    post_count_at_generation=thread.post_count,
                )
                .on_conflict_do_update(
                    index_elements=["thread_id"],
                    set_={
                        "summary_text": summary_text,
                        "post_count_at_generation": thread.post_count,
                    },
                )
            )
            await db.execute(stmt)
            await db.commit()
            logger.info("updated thread summary", thread_id=str(thread_id))
    except Exception:
        sentry_sdk.capture_exception()
        logger.exception("summarization failed", thread_id=str(thread_id))
