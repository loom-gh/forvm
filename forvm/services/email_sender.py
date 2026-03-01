from pathlib import Path

import resend
import structlog
from jinja2 import Environment, FileSystemLoader

from forvm.config import settings

logger = structlog.get_logger()

_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        templates_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
        _jinja_env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
        )
    return _jinja_env


async def send_email(to: str, subject: str, template_name: str, context: dict) -> None:
    if not settings.resend_api_key:
        logger.warning("resend_not_configured", to=to, subject=subject)
        return

    env = _get_jinja_env()
    template = env.get_template(template_name)
    body = template.render(**context)

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send({
            "from": settings.resend_from_address,
            "to": [to],
            "subject": subject,
            "text": body,
        })
        logger.info("email_sent", to=to, subject=subject)
    except Exception:
        logger.exception("email_send_failed", to=to, subject=subject)
        raise
