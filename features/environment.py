"""behave hooks: fresh rate-limit counters and a readiness probe on fakes."""

from datetime import UTC, datetime

from behave.model import Scenario
from behave.runner import Context
from fastapi import FastAPI
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import ReadinessReport
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr

from meritum_backend.health.api import get_readiness
from meritum_backend.health.models import Problems
from meritum_backend.health.readiness import ReadinessProbe
from meritum_backend.limits import limiter
from meritum_backend.settings import Settings


class _Database:
    async def reachable(self) -> bool:  # ruff: ignore[no-self-use] -- implements DatabaseProbe
        return True


class _BlobStore:
    def problems(self) -> Problems:  # ruff: ignore[no-self-use] -- implements BlobStoreProbe
        return Problems([], [])


def _use_ready_probe(context: Context, app: FastAPI) -> None:
    app.dependency_overrides[get_readiness] = lambda: context.probe
    report = ReadinessReport(
        missing_env=[], unavailable_providers=[], checked_at=datetime.now(UTC)
    )
    context.readiness_jobs.set_event(context.probe.workflow_id, READINESS_KEY, report)


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Reset the slowapi counters and build a readiness probe for the scenario.

    The probe has its own queue (``context.readiness_jobs``), so its job stays out
    of the checks' queue; steps set the worker's report on it, or call
    ``context.use_ready_probe(app)`` for a ready service.

    Args:
        context: the behave context; gets ``probe``, ``readiness_jobs`` and
            ``use_ready_probe``.
        scenario: the scenario about to run.

    Features:
        none (infrastructure)
    """
    del scenario
    limiter.reset()
    context.readiness_jobs = InMemoryJobQueue()
    settings = Settings(channel_hash_salt=SecretStr("salt"))
    context.probe = ReadinessProbe(
        settings, context.readiness_jobs, _Database(), _BlobStore()
    )
    context.use_ready_probe = lambda app: _use_ready_probe(context, app)
