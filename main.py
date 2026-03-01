import sentry_sdk

sentry_sdk.init(
    dsn="https://efe19be6287f11cdf121f1f504e47969@o4510967336271872.ingest.us.sentry.io/4510967340597248",
    send_default_pii=True,
)

import uvicorn  # noqa: E402

from forvm.app import create_app  # noqa: E402
from forvm.config import settings  # noqa: E402

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=True,
    )
