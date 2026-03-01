import json

import structlog

from forvm.config import settings
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import QUALITY_GATE_SYSTEM, QUALITY_GATE_USER

logger = structlog.get_logger()


async def check_quality(content: str, thread_title: str) -> dict:
    """Synchronous quality check. Returns {"score": float, "passed": bool, "rejection_reason": str|None}"""
    try:
        client = get_openai_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": QUALITY_GATE_SYSTEM},
                {
                    "role": "user",
                    "content": QUALITY_GATE_USER.format(
                        title=thread_title,
                        content=content[:settings.llm_max_content_quality_gate],
                        threshold=settings.quality_threshold,
                    ),
                },
            ],
            reasoning_effort="minimal",
            max_completion_tokens=10000,
        )
        raw = response.choices[0].message.content
        logger.debug("quality_gate llm response", finish_reason=response.choices[0].finish_reason, raw_content=repr(raw))
        result = json.loads(raw)
        score = max(0.0, min(1.0, float(result.get("score", 0.25))))
        rejection = result.get("rejection_reason")
        return {
            "score": score,
            "passed": score >= settings.quality_threshold,
            "rejection_reason": rejection if isinstance(rejection, str) else None,
        }
    except Exception:
        logger.exception("quality gate failed, defaulting to pass")
        return {"score": 0.25, "passed": True, "rejection_reason": None}
