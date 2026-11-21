"""FastAPI application (meritum-frontend's nginx proxies /api here)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dbos import DBOSClient
from fastapi import FastAPI
from meritum_core.jobs.adapters import DbosJobQueue
from meritum_core.jobs.contracts import APPLICATION_NAME

from meritum_backend.discord.api import router as discord_router
from meritum_backend.health.api import router as health_router
from meritum_backend.jobs.api import router as jobs_router
from meritum_backend.limits import RateLimitExceeded, limiter, too_many_requests
from meritum_backend.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app.

    Returns:
        The FastAPI app with its routers.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # lazy: no connection until the first job, so the API starts without the worker.
        client = DBOSClient(
            system_database_url=settings.dbos_url,
            dbos_system_schema=settings.dbos_schema,
            application_name=APPLICATION_NAME,
            lazy=True,
        )
        app.state.jobs = DbosJobQueue(client, app_version=settings.env)
        try:
            yield
        finally:
            client.destroy()

    app = FastAPI(
        title="Meritum API",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, too_many_requests)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(discord_router)
    return app
