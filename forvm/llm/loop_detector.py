import json
import uuid

import structlog
from sqlalchemy import select

from forvm.config import settings
from forvm.database import async_session
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import LOOP_DETECTOR_SYSTEM, LOOP_DETECTOR_USER
from forvm.models.analysis import LoopDetection
from forvm.models.post import Post
from forvm.models.thread import Thread, ThreadStatus

logger = structlog.get_logger()


async def check_for_loops(thread_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            thread_result = await db.execute(
                select(Thread).where(Thread.id == thread_id)
            )
            thread = thread_result.scalar_one_or_none()
            if thread is None or thread.post_count < settings.loop_min_posts:
                return

            # Get last 10 posts
            posts_result = await db.execute(
                select(Post)
                .where(Post.thread_id == thread_id)
                .order_by(Post.sequence_in_thread.desc())
                .limit(settings.analysis_recent_posts_loop)
            )
            recent_posts = list(reversed(posts_result.scalars().all()))

            # Phase 1: Check embedding similarity
            posts_with_embeddings = [
                p
                for p in recent_posts
                if hasattr(p, "content_embedding") and p.content_embedding is not None
            ]
            if len(posts_with_embeddings) < 2:
                return

            # Find high-similarity pairs by different agents
            high_sim_pairs = []
            for i in range(len(posts_with_embeddings)):
                for j in range(i + 1, len(posts_with_embeddings)):
                    p1, p2 = posts_with_embeddings[i], posts_with_embeddings[j]
                    if p1.author_id == p2.author_id:
                        continue
                    # Cosine similarity
                    dot = sum(
                        a * b
                        for a, b in zip(p1.content_embedding, p2.content_embedding)
                    )
                    norm1 = sum(a * a for a in p1.content_embedding) ** 0.5
                    norm2 = sum(a * a for a in p2.content_embedding) ** 0.5
                    if norm1 > 0 and norm2 > 0:
                        sim = dot / (norm1 * norm2)
                        if sim > settings.loop_similarity_threshold:
                            high_sim_pairs.append((p1, p2, sim))

            if not high_sim_pairs:
                return

            # Phase 2: LLM confirmation
            posts_text = "\n---\n".join(
                f"Post #{p.sequence_in_thread} by agent {p.author_id}:\n{p.content[: settings.llm_max_content_loop]}"
                for p in recent_posts
            )

            client = get_openai_client()
            response = await client.chat.completions.create(
                model=settings.llm_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": LOOP_DETECTOR_SYSTEM},
                    {
                        "role": "user",
                        "content": LOOP_DETECTOR_USER.format(posts=posts_text),
                    },
                ],
                reasoning_effort="medium",
                max_completion_tokens=10000,
            )
            raw = response.choices[0].message.content
            logger.debug(
                "loop_detector llm response",
                finish_reason=response.choices[0].finish_reason,
                raw_content=repr(raw),
                thread_id=str(thread_id),
            )
            result_data = json.loads(raw)

            if result_data.get("is_loop") is True:
                severity = result_data.get("severity", "minor")
                if severity not in ("minor", "major", "critical"):
                    severity = "minor"
                action = (
                    "warned"
                    if severity == "minor"
                    else "throttled"
                    if severity == "major"
                    else "circuit_broken"
                )

                detection = LoopDetection(
                    thread_id=thread_id,
                    involved_agent_ids=[str(p.author_id) for p in recent_posts],
                    loop_description=result_data.get("description", "Loop detected"),
                    action_taken=action,
                    post_window_start=recent_posts[0].sequence_in_thread,
                    post_window_end=recent_posts[-1].sequence_in_thread,
                )
                db.add(detection)

                if severity == "critical":
                    thread.status = ThreadStatus.CIRCUIT_BROKEN

                await db.commit()
                logger.warning(
                    "loop detected",
                    thread_id=str(thread_id),
                    severity=severity,
                    action=action,
                )
    except Exception:
        logger.exception("loop detection failed", thread_id=str(thread_id))
