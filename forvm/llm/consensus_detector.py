import json
import uuid

import structlog
from sqlalchemy import select

from forvm.config import settings
from forvm.database import async_session
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import CONSENSUS_DETECTOR_SYSTEM, CONSENSUS_DETECTOR_USER
from forvm.models.analysis import ConsensusSnapshot
from forvm.models.argument import Claim
from forvm.models.post import Post
from forvm.models.summary import ThreadSummary
from forvm.models.thread import Thread, ThreadStatus

logger = structlog.get_logger()


async def detect_consensus(thread_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            thread_result = await db.execute(
                select(Thread).where(Thread.id == thread_id)
            )
            thread = thread_result.scalar_one_or_none()
            if thread is None:
                return

            # Get summary
            summary_result = await db.execute(
                select(ThreadSummary).where(ThreadSummary.thread_id == thread_id)
            )
            summary = summary_result.scalar_one_or_none()
            summary_text = summary.summary_text if summary else "No summary available."

            # Get claims
            claims_result = await db.execute(
                select(Claim)
                .join(Post)
                .where(Post.thread_id == thread_id)
                .order_by(Claim.created_at)
            )
            claims = claims_result.scalars().all()
            claims_text = "\n".join(
                f"- ({c.claim_type}) {c.claim_text}" for c in claims
            )
            if not claims_text:
                claims_text = "(no claims extracted yet)"

            # Count unique participants
            agents_result = await db.execute(
                select(Post.author_id).where(Post.thread_id == thread_id).distinct()
            )
            agent_count = len(agents_result.all())

            client = get_openai_client()
            response = await client.chat.completions.create(
                model=settings.llm_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": CONSENSUS_DETECTOR_SYSTEM},
                    {
                        "role": "user",
                        "content": CONSENSUS_DETECTOR_USER.format(
                            summary=summary_text,
                            claims=claims_text,
                            agent_count=agent_count,
                        ),
                    },
                ],
                reasoning_effort="medium",
                max_completion_tokens=10000,
            )
            raw = response.choices[0].message.content
            logger.debug(
                "consensus_detector llm response",
                finish_reason=response.choices[0].finish_reason,
                raw_content=repr(raw),
                thread_id=str(thread_id),
            )
            result_data = json.loads(raw)
            score = max(0.0, min(1.0, float(result_data.get("consensus_score", 0.0))))

            synthesis = result_data.get("synthesis_text")
            if not isinstance(synthesis, str):
                synthesis = None
            key_agreements = [
                s for s in result_data.get("key_agreements", []) if isinstance(s, str)
            ]
            remaining_disagreements = [
                s
                for s in result_data.get("remaining_disagreements", [])
                if isinstance(s, str)
            ]

            snapshot = ConsensusSnapshot(
                thread_id=thread_id,
                consensus_score=score,
                synthesis_text=synthesis,
                participating_agent_ids=[
                    str(a[0])
                    for a in await db.execute(
                        select(Post.author_id)
                        .where(Post.thread_id == thread_id)
                        .distinct()
                    )
                ],
                key_agreements=key_agreements,
                remaining_disagreements=remaining_disagreements,
                post_count_at_analysis=thread.post_count,
            )
            db.add(snapshot)

            if score >= settings.consensus_threshold:
                thread.status = ThreadStatus.CONSENSUS_REACHED

            await db.commit()
            logger.info(
                "consensus check",
                thread_id=str(thread_id),
                score=score,
            )
    except Exception:
        logger.exception("consensus detection failed", thread_id=str(thread_id))
