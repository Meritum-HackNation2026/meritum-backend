"""Readiness of the service: the API's own variables and the worker's report.

The worker holds the model, search, transcription and fact-check keys, so the API
reads the worker's report through the `readiness` workflow (WorkerReports, ADR-03).
Only variable and provider names are reported, never their values.

Features:
    US-WDR-08, US-BEZ-03, F-30, ADR-03
"""

import logging
import time
from collections.abc import Callable

from meritum_core.jobs.ports import JobQueue
from pydantic import SecretStr

from meritum_backend.health.constants import (
    BOT_TOKEN_ENV,
    HEALTH_WORKER_WAIT_SECONDS,
    READY_CACHE_SECONDS,
    SALT_ENV,
    STARTUP_WORKER_WAIT_SECONDS,
)
from meritum_backend.health.models import Readiness
from meritum_backend.health.ports import BlobStoreProbe, DatabaseProbe
from meritum_backend.health.worker_reports import WorkerReports
from meritum_backend.settings import Settings

_logger = logging.getLogger(__name__)


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
        self._worker = WorkerReports(jobs, clock)
        self._last: tuple[float, Readiness] | None = None

    @property
    def workflow_id(self) -> str:
        """The `readiness` workflow the probe reads now.

        Returns:
            Its id; tests set the worker's event on it.
        """
        return self._worker.workflow_id

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
        worker = await self._worker.latest(worker_wait)
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

    def log_unstartable(self) -> None:
        """Log what the API's own configuration lacks when startup must stop.

        The worker is not asked: the process is about to exit.

        Features:
            US-WDR-08, US-BEZ-03, F-30
        """
        blob = self._blob_store.problems()
        _logger.error(
            "not ready, cannot start: missing env %s, unavailable %s",
            ", ".join(_settings_missing(self._settings) + blob.missing_env) or "none",
            ", ".join(blob.unavailable_providers) or "none",
        )
