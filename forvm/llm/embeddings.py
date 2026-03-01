import uuid

import sentry_sdk
import structlog
from sqlalchemy import select

from forvm.config import settings
from forvm.database import async_session
from forvm.llm.client import get_openai_client
from forvm.models.post import Post
from forvm.models.thread import Thread

logger = structlog.get_logger()


async def generate_embedding(text: str) -> list[float]:
    client = get_openai_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=text[: settings.llm_max_content_embedding],
    )
    return response.data[0].embedding


async def embed_post(post_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            result = await db.execute(select(Post).where(Post.id == post_id))
            post = result.scalar_one_or_none()
            if post is None:
                return

            embedding = await generate_embedding(post.content)
            post.content_embedding = embedding
            await db.commit()
            logger.info("embedded post", post_id=str(post_id))
    except Exception:
        sentry_sdk.capture_exception()
        logger.exception("failed to embed post", post_id=str(post_id))


async def embed_thread_title(thread_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            result = await db.execute(select(Thread).where(Thread.id == thread_id))
            thread = result.scalar_one_or_none()
            if thread is None:
                return

            embedding = await generate_embedding(thread.title)
            thread.title_embedding = embedding
            await db.commit()
            logger.info("embedded thread title", thread_id=str(thread_id))
    except Exception:
        sentry_sdk.capture_exception()
        logger.exception("failed to embed thread title", thread_id=str(thread_id))
