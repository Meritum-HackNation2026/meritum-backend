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

from meritum_backend.archives.api import router as archives_router
from meritum_backend.archives.factory import build_archive_store
from meritum_backend.auth.api import router as auth_router
from meritum_backend.auth.constants import (
    LOCAL_URL,
    PUBLIC_URLS,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    TOKEN_BYTES,
)
from meritum_backend.auth.factory import build_login
from meritum_backend.checks.api import audio_router, history_router, image_router
from meritum_backend.checks.api import events_router as check_events_router
from meritum_backend.checks.api import router as checks_router
from meritum_backend.checks.factory import build_blobs, build_result_cache
from meritum_backend.discord.api import router as discord_router
from meritum_backend.discord.factory import build_replies
from meritum_backend.evaluation.api import router as eval_router
from meritum_backend.evaluation.constants import PANEL_PATH
from meritum_backend.evaluation.factory import build_eval_store
from meritum_backend.export.api import router as export_router
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
from meritum_backend.mcp import (
    McpSettings,
    build_corpus_reader,
    build_mcp,
    build_mcp_auth,
)
from meritum_backend.mcp_oauth import OAuthServer, build_signer
from meritum_backend.mcp_oauth.api import metadata_router as oauth_metadata_router
from meritum_backend.mcp_oauth.api import router as oauth_router
from meritum_backend.mcp_oauth.constants import MCP_PATH, RESOURCE_METADATA_PATH
from meritum_backend.moderation import InMemoryAnswerStore, InMemorySourceDocuments
from meritum_backend.moderation.api import answer_router, handoff_router
from meritum_backend.moderation.api import router as moderation_router
from meritum_backend.moderation.factory import build_moderation
from meritum_backend.notifications.api import config_router as notifier_config_router
from meritum_backend.notifications.api import router as notifications_router
from meritum_backend.notifications.factory import build_announcer, build_config_store
from meritum_backend.privacy.access_log import mask_sessions_in_access_log
from meritum_backend.privacy.api import account_router
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
            async with mcp_app.lifespan(app):
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
    app.state.answers = InMemoryAnswerStore()
    app.state.source_documents = InMemorySourceDocuments()
    repositories = build_app_repositories(DatabaseSettings())
    app.state.repositories = repositories
    app.state.staff = build_staff(repositories)
    app.state.notifier_configs = build_config_store(settings)
    app.state.announcer = build_announcer(
        settings, repositories, app.state.notifier_configs
    )
    app.state.corpus_search, app.state.source_catalogue = build_corpus_reader()
    secret = settings.session_secret
    # no key configured: a random one, so sessions and MCP tokens end at restart
    key = (secret.get_secret_value() if secret is not None else "") or (
        secrets.token_urlsafe(TOKEN_BYTES)
    )
    base = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    app.state.mcp_oauth = OAuthServer(build_signer(key), base)
    app.state.mcp_resource_metadata = f"{base}{RESOURCE_METADATA_PATH}{MCP_PATH}"
    app.state.mcp_auth = build_mcp_auth(McpSettings(), extra=[app.state.mcp_oauth])
    app.state.mcp_corpus_version = settings.mcp_corpus_version
    app.state.eval_store = build_eval_store(settings)
    app.state.archives = build_archive_store(settings)
    app.state.eval_corpus_version = settings.eval_corpus_version
    app.state.eval_bundle_url = settings.eval_bundle_url or f"{base}{PANEL_PATH}"
    app.add_middleware(
        SessionMiddleware,
        secret_key=key,
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE,
        same_site="lax",
        https_only=True,
    )
    app.add_exception_handler(RateLimitExceeded, too_many_requests)
    app.add_exception_handler(CheckRefusedError, check_refused)
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(archives_router)
    app.include_router(discord_router)
    app.include_router(auth_router)
    app.include_router(checks_router)
    app.include_router(history_router)
    app.include_router(notifier_config_router)  # before staff: DELETE /staff/{email}
    app.include_router(staff_router)
    app.include_router(jury_router)
    app.include_router(moderation_router)
    app.include_router(answer_router)
    app.include_router(check_events_router)
    app.include_router(audio_router)
    app.include_router(image_router)
    app.include_router(privacy_router)
    app.include_router(account_router)
    app.include_router(handoff_router)
    app.include_router(sms_router)
    app.include_router(notifications_router)
    app.include_router(eval_router)
    app.include_router(export_router)
    app.include_router(oauth_metadata_router)
    app.include_router(oauth_router)
    mcp_app = build_mcp(app)
    app.router.routes.extend(
        mcp_app.routes
    )  # exactly /mcp: chat apps do not follow a redirect
    return app
