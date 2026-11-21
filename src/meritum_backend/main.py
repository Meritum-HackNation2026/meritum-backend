"""FastAPI application (meritum-frontend's nginx proxies /api here)."""

import asyncio
import contextlib
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dbos import DBOSClient
from fastapi import FastAPI
from meritum_core.jobs.adapters import DbosJobQueue
from meritum_core.jobs.contracts import APPLICATION_NAME
from meritum_core.observability import build_app_repositories
from meritum_core.security import PiiGateSettings, build_pii_gate
from meritum_core.shared.database import DatabaseSettings
from starlette.middleware.sessions import SessionMiddleware

from meritum_backend.auth.api import router as auth_router
from meritum_backend.auth.constants import SESSION_COOKIE, SESSION_MAX_AGE, TOKEN_BYTES
from meritum_backend.auth.factory import build_login
from meritum_backend.checks.api import audio_router
from meritum_backend.checks.api import events_router as check_events_router
from meritum_backend.checks.api import router as checks_router
from meritum_backend.checks.factory import build_blobs, build_result_cache
from meritum_backend.discord.api import router as discord_router
from meritum_backend.discord.factory import build_replies
from meritum_backend.health.api import router as health_router
from meritum_backend.health.factory import build_readiness
from meritum_backend.jobs.api import router as jobs_router
from meritum_backend.jury.api import router as jury_router
from meritum_backend.jury.factory import build_jury
from meritum_backend.limits import (
    CheckRefusedError,
    LimitSettings,
    RateLimitExceeded,
    build_check_gate,
    check_refused,
    limiter,
    start_pruning,
    too_many_requests,
)
from meritum_backend.moderation.api import handoff_router
from meritum_backend.moderation.api import router as moderation_router
from meritum_backend.moderation.factory import build_moderation
from meritum_backend.notifications.api import router as notifications_router
from meritum_backend.privacy.access_log import mask_sessions_in_access_log
from meritum_backend.privacy.api import router as privacy_router
from meritum_backend.settings import Settings
from meritum_backend.sms.api import router as sms_router
from meritum_backend.sms.factory import build_sms
from meritum_backend.staff.api import router as staff_router
from meritum_backend.staff.factory import build_staff


def create_app(settings: Settings | None = None) -> FastAPI:  # ruff: ignore[too-many-statements]  # composition root: one line per slice it wires
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
        # lazy: no connection until the first job, so the API starts without the worker;
        # no retries: an unreachable database is a 503, not a request blocked for long.
        client = DBOSClient(
            system_database_url=settings.dbos_url,
            dbos_system_schema=settings.dbos_schema,
            application_name=APPLICATION_NAME,
            lazy=True,
            retry_connection_errors=False,
        )
        app.state.jobs = DbosJobQueue(client, app_version=settings.env)
        app.state.readiness = build_readiness(settings, app.state.jobs)
        try:
            app.state.blobs = build_blobs(settings)
        except Exception:
            # name the missing variables before a misconfigured deploy stops (#19)
            app.state.readiness.log_unstartable()
            raise
        app.state.check_gate = build_check_gate(settings, LimitSettings(), client)
        startup_log = asyncio.create_task(app.state.readiness.log_startup())
        pruner = start_pruning(app.state.check_gate)
        try:
            yield
        finally:
            for task in (pruner, startup_log):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            client.destroy()

    app = FastAPI(
        title="Meritum API",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    mask_sessions_in_access_log()
    app.state.limiter = limiter
    (app.state.jury_links, app.state.jury_rate_counter, app.state.jury_rate_secret) = (
        build_jury(settings)
    )
    app.state.login = build_login(settings)
    app.state.result_cache = build_result_cache(settings)
    app.state.pii_gate = build_pii_gate(PiiGateSettings())  # null gate by default
    app.state.admin_emails = settings.admin_emails
    app.state.sms = build_sms(settings)
    app.state.discord_replies = build_replies()
    app.state.cases, app.state.topics = build_moderation()
    repositories = build_app_repositories(DatabaseSettings())
    app.state.repositories = repositories
    app.state.staff = build_staff(repositories)
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
    app.add_exception_handler(CheckRefusedError, check_refused)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(discord_router)
    app.include_router(auth_router)
    app.include_router(checks_router)
    app.include_router(staff_router)
    app.include_router(jury_router)
    app.include_router(moderation_router)
    app.include_router(check_events_router)
    app.include_router(audio_router)
    app.include_router(privacy_router)
    app.include_router(handoff_router)
    app.include_router(sms_router)
    app.include_router(notifications_router)
    return app
