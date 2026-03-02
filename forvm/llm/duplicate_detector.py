import json

import sentry_sdk
import structlog

from forvm.config import settings
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import DEDUP_CHECK_SYSTEM, DEDUP_CHECK_USER

logger = structlog.get_logger()


async def check_duplicate(content: str, previous_content: str) -> dict:
    """Check if a new post is semantically equivalent to the previous post.

    Returns {"score": float, "passed": bool, "explanation": str | None}
    """
    try:
        client = get_openai_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": DEDUP_CHECK_SYSTEM},
                {
                    "role": "user",
                    "content": DEDUP_CHECK_USER.format(
                        post_a=previous_content[: settings.llm_max_content_dedup],
                        post_b=content[: settings.llm_max_content_dedup],
                        threshold=settings.dedup_similarity_threshold,
                    ),
                },
            ],
            reasoning_effort="minimal",
            max_completion_tokens=10000,
        )
        raw = response.choices[0].message.content
        logger.debug(
            "duplicate_detector llm response",
            finish_reason=response.choices[0].finish_reason,
            raw_content=repr(raw),
        )
        result = json.loads(raw)
        score = max(0.0, min(1.0, float(result.get("score", 0.0))))
        explanation = result.get("explanation")
        return {
            "score": score,
            "passed": score < settings.dedup_similarity_threshold,
            "explanation": explanation if isinstance(explanation, str) else None,
        }
    except Exception:
        sentry_sdk.capture_exception()
        logger.exception("duplicate check failed, defaulting to pass")
        return {"score": 0.0, "passed": True, "explanation": None}
