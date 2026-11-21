"""Builds the readiness probe with its database and blob store adapters.

Features:
    US-WDR-08, US-BEZ-03, F-30
"""

from meritum_core.jobs.ports import JobQueue

from meritum_backend.health.adapters import BlobStoreConfig, PostgresProbe
from meritum_backend.health.readiness import ReadinessProbe
from meritum_backend.settings import Settings


def build_readiness(settings: Settings, jobs: JobQueue) -> ReadinessProbe:
    """Build the probe the app keeps for /api/v1/health and the checks.

    Args:
        settings: the app settings.
        jobs: the job queue the worker's report comes through.

    Returns:
        The readiness probe.

    Features:
        US-WDR-08, US-BEZ-03, F-30
    """
    return ReadinessProbe(
        settings, jobs, PostgresProbe(settings.database_url), BlobStoreConfig(settings)
    )
