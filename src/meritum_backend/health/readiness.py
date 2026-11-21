"""Readiness of the service: the API's own variables and the worker's report.

The worker holds the model, search, transcription and fact-check keys, so the API
enqueues the `readiness` workflow and reads its event (ADR-03). It enqueues a new one
when the last report is older than WORKER_REFRESH_SECONDS, so a restarted worker
is seen.
Only variable and provider names are reported, never their values.

Features:
    US-WDR-08, US-BEZ-03, F-30, ADR-03
"""

import asyncio
import logging
import time
from collections.abc import Callable
from uuid import uuid4

from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import READINESS, ReadinessInput, ReadinessReport
from meritum_core.jobs.ports import JobQueue
from pydantic import SecretStr

from meritum_backend.health.constants import (
    BOT_TOKEN_ENV,
    HEALTH_WORKER_WAIT_SECONDS,
    READY_CACHE_SECONDS,
    SALT_ENV,
    STARTUP_WORKER_WAIT_SECONDS,
    WORKER_REFRESH_SECONDS,
    WORKFLOW_ID_PREFIX,
)
from meritum_backend.health.models import Readiness
from meritum_backend.health.ports import BlobStoreProbe, DatabaseProbe
from meritum_backend.settings import Settings

_logger = logging.getLogger(__name__)


def _new_workflow_id() -> str:
    return f"{WORKFLOW_ID_PREFIX}{uuid4().hex}"


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

    Attributes:
        workflow_id: the `readiness` workflow the probe reads; replaced by a new one
            when the worker's report is older than WORKER_REFRESH_SECONDS.

    Args:
        settings: the app settings.
        jobs: the job queue the worker's report comes through.
        database: whether the API's database role can run a query.
        blob_store: what the blob store configuration lacks.
        clock: monotonic seconds; a fake one in tests.

    Features:
        US-WDR-08, US-BEZ-03, F-30, ADR-03
    """

    def __init__(
        self,
        settings: Settings,
        jobs: JobQueue,
        database: DatabaseProbe,
        blob_store: BlobStoreProbe,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._jobs = jobs
        self._database = database
        self._blob_store = blob_store
        self._clock = clock
        self._refreshed_at: float | None = None  # when the pending refresh was enqueued
        self._enqueued = False
        self._last: tuple[float, Readiness] | None = None
        # (workflow id, when its report arrived, the report)
        self._report: tuple[str, float, ReadinessReport] | None = None
        self.workflow_id = _new_workflow_id()

    async def _read_event(self, wait: float) -> ReadinessReport | None:
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

    def _refresh_if_due(self) -> None:
        if self._report is None or self._report[0] != self.workflow_id:
            return  # no report yet, or a refresh is already pending
        if self._clock() - self._report[1] >= WORKER_REFRESH_SECONDS:
            # a restarted worker answers a new workflow; keep the last report meanwhile
            self.workflow_id = _new_workflow_id()
            self._enqueued = False
            self._refreshed_at = self._clock()

    async def _worker_report(self, wait: float) -> ReadinessReport | None:
        self._refresh_if_due()
        report = await self._read_event(wait)
        is_new = self._report is None or self._report[0] != self.workflow_id
        if report is not None and is_new:
            self._report = (self.workflow_id, self._clock(), report)
            self._refreshed_at = None
        # a worker that left a refresh unanswered for a whole period is not reported
        unanswered = self._refreshed_at is not None and (
            self._clock() - self._refreshed_at >= WORKER_REFRESH_SECONDS
        )
        return None if unanswered or self._report is None else self._report[2]

    async def check(self, worker_wait: float = HEALTH_WORKER_WAIT_SECONDS) -> Readiness:
        """Probe the database, the API's variables and the worker's report.

        Args:
            worker_wait: how long to wait for the worker's report, in seconds.

        Returns:
            The report; ``status`` is ok only when nothing is missing.

        Features:
            US-WDR-08, US-BEZ-03, F-30
        """
        database_ok = await self._database.reachable()
        blob = self._blob_store.problems()
        worker = await self._worker_report(worker_wait)
        missing = _settings_missing(self._settings) + blob.missing_env
        unavailable = list(blob.unavailable_providers)
        if worker is not None:
            missing += worker.missing_env
            unavailable += worker.unavailable_providers
        missing, unavailable = (
            list(dict.fromkeys(missing)),
            list(dict.fromkeys(unavailable)),
        )
        ok = database_ok and worker is not None and not missing and not unavailable
        readiness = Readiness(
            status="ok" if ok else "degraded",
            env=self._settings.env,
            database="ok" if database_ok else "unavailable",
            worker="ok" if worker is not None else "not_reported",
            missing_env=missing,
            unavailable_providers=unavailable,
        )
        self._last = (self._clock(), readiness)
        return readiness

    async def ready(self) -> bool:
        """Whether checks may run; reuses a report younger than the cache window.

        Returns:
            True when the last report is ok.

        Features:
            US-WDR-08, US-BEZ-03, F-30
        """
        if self._last and self._clock() - self._last[0] < READY_CACHE_SECONDS:
            return self._last[1].ready
        return (await self.check()).ready

    async def log_startup(self) -> None:
        """Log the report once the worker answered or the startup wait ran out.

        Features:
            US-WDR-08, US-BEZ-03, F-30
        """
        readiness = await self.check(STARTUP_WORKER_WAIT_SECONDS)
        if readiness.ready:
            _logger.info("ready (env %s)", readiness.env)
            return
        _logger.warning(
            "not ready: database %s, worker %s, missing env %s, unavailable %s",
            readiness.database,
            readiness.worker,
            ", ".join(readiness.missing_env) or "none",
            ", ".join(readiness.unavailable_providers) or "none",
        )
