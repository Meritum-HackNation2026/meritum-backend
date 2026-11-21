"""behave hooks: fresh rate-limit counters and a readiness probe on fakes."""

from behave.model import Scenario
from behave.runner import Context
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr

from meritum_backend.health.readiness import Problems, ReadinessProbe
from meritum_backend.limits import limiter
from meritum_backend.settings import Settings


async def _database_ok() -> bool:  # ruff: ignore[unused-async] -- the probe awaits its database check
    return True


def before_scenario(context: Context, scenario: Scenario) -> None:
    """Reset the slowapi counters and build a readiness probe for the scenario.

    The probe has its own queue (``context.readiness_jobs``), so its job stays out
    of the checks' queue; steps set the worker's report on it.

    Args:
        context: the behave context; gets ``probe`` and ``readiness_jobs``.
        scenario: the scenario about to run.

    Features:
        none (infrastructure)
    """
    del scenario
    limiter.reset()
    context.readiness_jobs = InMemoryJobQueue()
    settings = Settings(channel_hash_salt=SecretStr("salt"))
    context.probe = ReadinessProbe(
        settings, context.readiness_jobs, _database_ok, lambda: Problems([], [])
    )
