import json

import sentry_sdk
import structlog

from forvm.config import settings
from forvm.llm.client import get_openai_client
from forvm.llm.prompts import SAFETY_SCREEN_SYSTEM, SAFETY_SCREEN_USER

logger = structlog.get_logger()


async def check_safety(text: str) -> dict:
    """Classify text for prompt injection / hijack attempts.

    Returns {"safe": bool, "category": str|None, "explanation": str|None}
    """
    if not settings.safety_screen_enabled:
        return {"safe": True, "category": None, "explanation": None}

    try:
        client = get_openai_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SAFETY_SCREEN_SYSTEM},
                {
                    "role": "user",
                    "content": SAFETY_SCREEN_USER.format(
                        text=text[: settings.llm_max_content_safety_screen],
                    ),
                },
            ],
            reasoning_effort="minimal",
            max_completion_tokens=10000,
        )
        raw = response.choices[0].message.content
        logger.debug(
            "safety_screen llm response",
            finish_reason=response.choices[0].finish_reason,
            raw_content=repr(raw),
        )
        result = json.loads(raw)
        safe = bool(result.get("safe", True))
        category = result.get("category")
        explanation = result.get("explanation")
        verdict = {
            "safe": safe,
            "category": category if isinstance(category, str) and not safe else None,
            "explanation": (
                explanation if isinstance(explanation, str) and not safe else None
            ),
        }
        if not safe:
            logger.warning(
                "safety screen rejected content",
                category=verdict["category"],
                explanation=verdict["explanation"],
            )
            with sentry_sdk.push_scope() as scope:
                scope.set_extra("category", verdict["category"])
                scope.set_extra("explanation", verdict["explanation"])
                scope.set_extra("text_preview", text[:500])
                sentry_sdk.capture_message(
                    f"Safety screen blocked content: {verdict['category']}",
                    level="warning",
                )
        return verdict
    except Exception:
        sentry_sdk.capture_exception()
        logger.exception("safety screen failed, defaulting to pass")
        return {"safe": True, "category": None, "explanation": None}
