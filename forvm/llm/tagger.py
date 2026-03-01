import json
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from forvm.config import settings
from forvm.database import async_session
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import TAGGER_SYSTEM, TAGGER_USER
from forvm.models.post import Post
from forvm.models.tag import PostTag, Tag

logger = structlog.get_logger()


async def auto_tag_post(post_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            result = await db.execute(select(Post).where(Post.id == post_id))
            post = result.scalar_one_or_none()
            if post is None:
                return

            # Get existing tags
            tag_result = await db.execute(select(Tag.name).limit(settings.analysis_tags_limit))
            existing_tags = [row[0] for row in tag_result.all()]

            client = get_openai_client()
            response = await client.chat.completions.create(
                model=settings.llm_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": TAGGER_SYSTEM},
                    {
                        "role": "user",
                        "content": TAGGER_USER.format(
                            existing_tags=", ".join(existing_tags) if existing_tags else "(none yet)",
                            content=post.content[:settings.llm_max_content_tagger],
                        ),
                    },
                ],
                reasoning_effort="minimal",
                max_completion_tokens=10000,
            )
            raw = response.choices[0].message.content
            logger.debug("tagger llm response", finish_reason=response.choices[0].finish_reason, raw_content=repr(raw), post_id=str(post_id))
            result_data = json.loads(raw)

            # Validate and apply existing tags
            for tag_info in result_data.get("existing_tags", []):
                if not isinstance(tag_info, dict) or not isinstance(tag_info.get("name"), str):
                    continue
                tag_name = tag_info["name"]
                tag_result = await db.execute(
                    select(Tag).where(Tag.name == tag_name)
                )
                tag = tag_result.scalar_one_or_none()
                if tag:
                    confidence = tag_info.get("confidence", 0.8)
                    confidence = max(0.0, min(1.0, float(confidence)))
                    post_tag = PostTag(
                        tag_id=tag.id,
                        post_id=post.id,
                        thread_id=post.thread_id,
                        confidence=confidence,
                        is_auto=True,
                    )
                    db.add(post_tag)

            # Create new tags
            for new_tag_info in result_data.get("new_tags", []):
                if not isinstance(new_tag_info, dict) or not isinstance(new_tag_info.get("name"), str):
                    continue
                tag = Tag(
                    name=new_tag_info["name"],
                    description=new_tag_info.get("description"),
                )
                db.add(tag)
                await db.flush()
                post_tag = PostTag(
                    tag_id=tag.id,
                    post_id=post.id,
                    thread_id=post.thread_id,
                    confidence=0.7,
                    is_auto=True,
                )
                db.add(post_tag)

            await db.commit()
            logger.info("auto-tagged post", post_id=str(post_id))
    except Exception:
        logger.exception("auto-tagging failed", post_id=str(post_id))
