"""Readiness of the service: the API's own variables and the worker's report.

The worker holds the model, search, transcription and fact-check keys, so the API
enqueues the `readiness` workflow once per process and reads its event (ADR-03).
Only variable and provider names are reported, never their values.

Features:
    US-WDR-08, US-BEZ-03, F-30, ADR-03
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Literal, NamedTuple
from uuid import uuid4

from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import READINESS, ReadinessInput, ReadinessReport
from meritum_core.jobs.ports import JobQueue
from pydantic import BaseModel, SecretStr

from meritum_backend.health.constants import (
    BOT_TOKEN_ENV,
    HEALTH_WORKER_WAIT_SECONDS,
    NOT_READY_CODE,
    NOT_READY_KEY,
    READY_CACHE_SECONDS,
    SALT_ENV,
    STARTUP_WORKER_WAIT_SECONDS,
    WORKFLOW_ID_PREFIX,
)
from meritum_backend.settings import Settings

_logger = logging.getLogger(__name__)


class Problems(NamedTuple):
    """What one part of the service lacks.

    Attributes:
        missing_env: names of unset required variables.
        unavailable_providers: providers that are configured but unusable.

    Features:
        US-WDR-08, F-30
    """

    missing_env: list[str]
    unavailable_providers: list[str]


class Readiness(BaseModel):
    """Body of GET /api/v1/health: what the API and the worker lack.

    Attributes:
        status: ok when nothing is missing, otherwise degraded.
        env: the environment name.
        database: whether the API's database role can run a query.
        worker: whether the worker published its readiness report.
        missing_env: names of unset required variables (API and worker).
        unavailable_providers: providers the API or the worker cannot use.

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """

    status: Literal["ok", "degraded"]
    env: str
    database: Literal["ok", "unavailable"]
    worker: Literal["ok", "not_reported"]
    missing_env: list[str]
    unavailable_providers: list[str]


class NotReady(BaseModel):
    """503 answer to a check while the service is not ready; names no keys.

    Attributes:
        status: always technical_failure, which is not a verdict.
        code: always not_ready.
        message_key: the copy/pl.json key to show.

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """

    status: Literal["technical_failure"] = "technical_failure"
    # shortcut: a plain string until core contract v4 (core#27) types failure codes.
    code: str = NOT_READY_CODE
    message_key: str = NOT_READY_KEY


def _unset(secret: SecretStr | None) -> bool:
    return secret is None or not secret.get_secret_value()


def _settings_missing(settings: Settings) -> list[str]:
    missing = [SALT_ENV] if _unset(settings.channel_hash_salt) else []
    discord_on = settings.discord_public_key is not None
    if discord_on and _unset(settings.discord_bot_token):
        missing.append(BOT_TOKEN_ENV)
    return missing


class ReadinessProbe:
    """Builds the readiness report of the API and the worker.

    Args:
        settings: the app settings.
        jobs: the job queue the worker's report comes through.
        database: answers whether the API's database role can run a query.
        blob_store: what the blob store configuration lacks.

    Features:
        US-WDR-08, US-BEZ-03, F-30, ADR-03
    """

    def __init__(
        self,
        settings: Settings,
        jobs: JobQueue,
        database: Callable[[], Awaitable[bool]],
        blob_store: Callable[[], Problems],
    ) -> None:
        self._settings = settings
        self._jobs = jobs
        self._database = database
        self._blob_store = blob_store
        self._enqueued = False
        self._last: tuple[float, Readiness] | None = None
        self.workflow_id = f"{WORKFLOW_ID_PREFIX}{uuid4().hex}"

    async def _worker_report(self, wait: float) -> ReadinessReport | None:
        try:
            async with asyncio.timeout(wait):
                if not self._enqueued:
                    payload = ReadinessInput()
                    await self._jobs.enqueue(
                        READINESS, payload, workflow_id=self.workflow_id
                    )
                    self._enqueued = True
                return await self._jobs.event(
                    self.workflow_id,
                    READINESS_KEY,
                    ReadinessReport,
                    timeout_seconds=wait,
                )
        except Exception as exc:  # ruff: ignore[blind-except] -- DBOS wraps driver errors; a bad report is no report
            _logger.warning(
                "worker readiness report unreadable: %s", type(exc).__name__
            )
            return None

    async def check(self, worker_wait: float = HEALTH_WORKER_WAIT_SECONDS) -> Readiness:
        """Probe the database, the API's variables and the worker's report.

        Args:
            worker_wait: how long to wait for the worker's report, in seconds.

        Returns:
            The report; ``status`` is ok only when nothing is missing.

        Features:
            US-WDR-08, US-BEZ-03, F-30
        """
        database_ok = await self._database()
        blob = self._blob_store()
        worker = await self._worker_report(worker_wait)
        missing = _settings_missing(self._settings) + blob.missing_env
        unavailable = list(blob.unavailable_providers)
        if worker is not None:
            missing += worker.missing_env
            unavailable += worker.unavailable_providers
        ok = database_ok and worker is not None and not missing and not unavailable
        readiness = Readiness(
            status="ok" if ok else "degraded",
            env=self._settings.env,
            database="ok" if database_ok else "unavailable",
            worker="ok" if worker is not None else "not_reported",
            missing_env=missing,
            unavailable_providers=unavailable,
        )
        self._last = (time.monotonic(), readiness)
        return readiness

    async def ready(self) -> bool:
        """Whether checks may run; reuses a report younger than the cache window.

        Returns:
            True when the last report is ok.

        Features:
            US-WDR-08, US-BEZ-03, F-30
        """
        if self._last and time.monotonic() - self._last[0] < READY_CACHE_SECONDS:
            return self._last[1].status == "ok"
        return (await self.check()).status == "ok"

    async def log_startup(self) -> None:
        """Log the report once the worker answered or the startup wait ran out.

        Features:
            US-WDR-08, US-BEZ-03, F-30
        """
        readiness = await self.check(STARTUP_WORKER_WAIT_SECONDS)
        if readiness.status == "ok":
            _logger.info("ready (env %s)", readiness.env)
            return
        _logger.warning(
            "not ready: database %s, worker %s, missing env %s, unavailable %s",
            readiness.database,
            readiness.worker,
            ", ".join(readiness.missing_env) or "none",
            ", ".join(readiness.unavailable_providers) or "none",
        )
