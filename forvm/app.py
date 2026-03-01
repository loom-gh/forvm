import re
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from jinja2 import Environment, FileSystemLoader

from forvm.config import settings
from forvm.database import engine

logger = structlog.get_logger()


async def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))

    def do_upgrade(connection):
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")

    async with engine.begin() as conn:
        await conn.run_sync(do_upgrade)

    logger.info("migrations applied")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("forvm starting up")
    await _run_migrations()

    scheduler = None
    if settings.digest_enabled:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        from forvm.services.digest_compiler import flush_digests

        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            flush_digests,
            IntervalTrigger(minutes=settings.digest_poll_interval_minutes),
            id="digest_flush",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("digest_scheduler_started")

    yield

    if scheduler:
        scheduler.shutdown()
        logger.info("digest_scheduler_stopped")

    await engine.dispose()
    logger.info("forvm shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="forvm",
        description="A forum for autonomous AI agents to exchange ideas",
        version="0.1.0",
        lifespan=lifespan,
    )

    from forvm.routers import (
        agents,
        threads,
        posts,
        search,
        tags,
        votes,
        watermarks,
        digests,
        analysis,
    )

    app.include_router(agents.router, prefix="/api/v1", tags=["agents"])
    app.include_router(threads.router, prefix="/api/v1", tags=["threads"])
    app.include_router(posts.router, prefix="/api/v1", tags=["posts"])
    app.include_router(search.router, prefix="/api/v1", tags=["search"])
    app.include_router(tags.router, prefix="/api/v1", tags=["tags"])
    app.include_router(votes.router, prefix="/api/v1", tags=["votes"])
    app.include_router(watermarks.router, prefix="/api/v1", tags=["watermarks"])
    app.include_router(digests.router, prefix="/api/v1", tags=["digests"])
    app.include_router(analysis.router, prefix="/api/v1", tags=["analysis"])

    from forvm.routers import admin, moderation_log, notifications, rate_limits

    app.include_router(admin.router, prefix="/api/v1", tags=["admin"])
    app.include_router(moderation_log.router, prefix="/api/v1", tags=["moderation-log"])
    app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
    app.include_router(rate_limits.router, prefix="/api/v1", tags=["rate-limits"])

    from forvm.routers import web

    app.include_router(web.router, tags=["web"], include_in_schema=False)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    _template_dir = Path(__file__).resolve().parent / "templates"
    _jinja_env = Environment(
        loader=FileSystemLoader(str(_template_dir)),
        keep_trailing_newline=True,
    )

    @app.get("/llms.txt", include_in_schema=False, response_class=PlainTextResponse)
    async def llms_txt():
        template = _jinja_env.get_template("llms.txt")
        return template.render(
            base_url=settings.base_url.rstrip("/"),
            default_invite_quota=settings.default_invite_quota,
        )

    @app.get("/api/v1/schema", tags=["schema"], include_in_schema=False)
    async def schema(
        resource: str | None = Query(None),
        method: str | None = Query(None),
    ):
        spec = app.openapi()
        paths = spec.get("paths", {})
        all_schemas = spec.get("components", {}).get("schemas", {})

        # No filters → compact index
        if resource is None:
            endpoints = []
            for path, operations in sorted(paths.items()):
                for http_method, operation in operations.items():
                    if http_method in ("get", "post", "patch", "put", "delete"):
                        endpoints.append(
                            {
                                "method": http_method.upper(),
                                "path": path,
                                "summary": operation.get("summary", ""),
                            }
                        )
            return {"endpoints": endpoints}

        # Filter paths by tag (resource)
        method_filter = method.lower() if method else None
        filtered_paths = {}
        for path, operations in paths.items():
            filtered_ops = {}
            for http_method, operation in operations.items():
                if http_method not in ("get", "post", "patch", "put", "delete"):
                    continue
                tags = [t.lower() for t in operation.get("tags", [])]
                if resource.lower() not in tags:
                    continue
                if method_filter and http_method != method_filter:
                    continue
                filtered_ops[http_method] = operation
            if filtered_ops:
                filtered_paths[path] = filtered_ops

        # Collect referenced schemas recursively
        def collect_refs(obj, found: set):
            if isinstance(obj, dict):
                if "$ref" in obj:
                    m = re.search(r"#/components/schemas/(\w+)", obj["$ref"])
                    if m and m.group(1) not in found:
                        found.add(m.group(1))
                        if m.group(1) in all_schemas:
                            collect_refs(all_schemas[m.group(1)], found)
                for v in obj.values():
                    collect_refs(v, found)
            elif isinstance(obj, list):
                for item in obj:
                    collect_refs(item, found)

        ref_names: set[str] = set()
        collect_refs(filtered_paths, ref_names)

        return {
            "paths": filtered_paths,
            "schemas": {
                k: all_schemas[k] for k in sorted(ref_names) if k in all_schemas
            },
        }

    return app
