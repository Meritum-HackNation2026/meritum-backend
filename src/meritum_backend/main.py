"""FastAPI application (meritum-frontend's nginx proxies /api here)."""

import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dbos import DBOSClient
from fastapi import FastAPI
from meritum_core.jobs.adapters import DbosJobQueue
from meritum_core.jobs.contracts import APPLICATION_NAME
from meritum_core.moderation.fakes import (
    InMemoryHighRiskTopicRepository,
    InMemoryModeratorCaseRepository,
)
from starlette.middleware.sessions import SessionMiddleware

from meritum_backend.auth.api import router as auth_router
from meritum_backend.auth.constants import SESSION_COOKIE, SESSION_MAX_AGE, TOKEN_BYTES
from meritum_backend.auth.factory import build_login
from meritum_backend.checks.api import router as checks_router
from meritum_backend.discord.api import router as discord_router
from meritum_backend.health.api import router as health_router
from meritum_backend.jobs.api import router as jobs_router
from meritum_backend.limits import RateLimitExceeded, limiter, too_many_requests
from meritum_backend.moderation.api import router as moderation_router
from meritum_backend.settings import Settings
from meritum_backend.staff.api import router as staff_router
from meritum_backend.staff.factory import build_staff


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app: the composition root that wires adapters from settings.

    Args:
        settings: the settings; read from the environment when None.

    Returns:
        The FastAPI app with its routers.

    Features:
        ADR-01
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
    app.state.login = build_login(settings)
    app.state.admin_emails = settings.admin_emails
    app.state.staff = build_staff()
    # shortcut: in memory, so the worker does not see them; PostgreSQL with core/031.
    app.state.topics = InMemoryHighRiskTopicRepository()
    app.state.cases = InMemoryModeratorCaseRepository()
    secret = settings.session_secret
    key = secret.get_secret_value() if secret is not None else ""
    app.add_middleware(
        SessionMiddleware,
        # no key configured: a random one, so sessions end when the process restarts
        secret_key=key or secrets.token_urlsafe(TOKEN_BYTES),
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE,
        same_site="lax",
        https_only=True,
    )
    app.add_exception_handler(RateLimitExceeded, too_many_requests)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(discord_router)
    app.include_router(auth_router)
    app.include_router(checks_router)
    app.include_router(staff_router)
    app.include_router(moderation_router)
    return app
