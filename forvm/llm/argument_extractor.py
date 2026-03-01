import json
import uuid

import structlog
from sqlalchemy import select

from forvm.config import settings
from forvm.database import async_session
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import ARGUMENT_EXTRACTOR_SYSTEM, ARGUMENT_EXTRACTOR_USER
from forvm.models.argument import Claim
from forvm.models.post import Post

logger = structlog.get_logger()


async def extract_arguments(post_id: uuid.UUID) -> None:
    try:
        async with async_session() as db:
            result = await db.execute(select(Post).where(Post.id == post_id))
            post = result.scalar_one_or_none()
            if post is None:
                return

            # Get recent claims in the thread
            claims_result = await db.execute(
                select(Claim)
                .join(Post)
                .where(Post.thread_id == post.thread_id)
                .order_by(Claim.created_at.desc())
                .limit(settings.analysis_recent_claims_limit)
            )
            recent_claims = claims_result.scalars().all()

            recent_claims_text = "\n".join(
                f"[{i}] ({c.claim_type}) {c.claim_text}"
                for i, c in enumerate(reversed(list(recent_claims)))
            )
            if not recent_claims_text:
                recent_claims_text = "(no prior claims)"

            client = get_openai_client()
            response = await client.chat.completions.create(
                model=settings.llm_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": ARGUMENT_EXTRACTOR_SYSTEM},
                    {
                        "role": "user",
                        "content": ARGUMENT_EXTRACTOR_USER.format(
                            recent_claims=recent_claims_text,
                            content=post.content[:settings.llm_max_content_argument],
                        ),
                    },
                ],
                reasoning_effort="medium",
                max_completion_tokens=10000,
            )
            raw = response.choices[0].message.content
            logger.debug("argument_extractor llm response", finish_reason=response.choices[0].finish_reason, raw_content=repr(raw), post_id=str(post_id))
            result_data = json.loads(raw)

            valid_types = {"assertion", "evidence", "rebuttal", "concession"}
            for claim_data in result_data.get("claims", []):
                if not isinstance(claim_data, dict) or not isinstance(claim_data.get("claim_text"), str):
                    continue
                claim_type = claim_data.get("type", "assertion")
                if claim_type not in valid_types:
                    claim_type = "assertion"
                novelty = claim_data.get("novelty_score")
                if novelty is not None:
                    novelty = max(0.0, min(1.0, float(novelty)))
                claim = Claim(
                    post_id=post.id,
                    claim_text=claim_data["claim_text"],
                    claim_type=claim_type,
                    supports_post_ids=claim_data.get("supports_claim_ids", []),
                    opposes_post_ids=claim_data.get("opposes_claim_ids", []),
                    novelty_score=novelty,
                )
                db.add(claim)

            # Update post novelty score (average of claim novelty scores)
            scores = [
                max(0.0, min(1.0, float(c.get("novelty_score", 0.5))))
                for c in result_data.get("claims", [])
                if isinstance(c, dict) and c.get("novelty_score") is not None
            ]
            if scores:
                post.novelty_score = sum(scores) / len(scores)

            await db.commit()
            logger.info("extracted arguments", post_id=str(post_id))
    except Exception:
        logger.exception("argument extraction failed", post_id=str(post_id))
