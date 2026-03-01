import httpx
import structlog

from forvm.config import settings

logger = structlog.get_logger()


async def send_webhook(url: str, payload: dict) -> None:
    timeout = httpx.Timeout(settings.webhook_timeout_seconds)
    max_attempts = settings.webhook_max_retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "forvm/0.1.0",
                    },
                )
                response.raise_for_status()
                logger.info("webhook_delivered", url=url, status=response.status_code)
                return
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(
                "webhook_delivery_failed",
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(exc),
            )
            if attempt == max_attempts:
                raise
