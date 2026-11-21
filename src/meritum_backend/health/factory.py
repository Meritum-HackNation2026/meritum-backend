"""Builds the readiness probe with its database and blob store checks.

Features:
    US-WDR-08, US-BEZ-03, F-30
"""

from functools import partial

import psycopg
from meritum_core.jobs.ports import JobQueue
from meritum_core.shared.blobs.constants import ENV_PREFIX
from meritum_core.shared.blobs.errors import BlobError
from meritum_core.shared.blobs.factory import build_blob_store
from meritum_core.shared.blobs.settings import BlobSettings
from pydantic import ValidationError

from meritum_backend.health.constants import BLOB_PROVIDER_FIELDS, BLOB_STORE
from meritum_backend.health.readiness import Problems, ReadinessProbe
from meritum_backend.settings import Settings


async def database_reachable(url: str) -> bool:
    """Whether the API's database role can run a query.

    Args:
        url: the database URL.

    Returns:
        True when ``SELECT 1`` succeeded.

    Features:
        US-WDR-08, F-30
    """
    try:
        async with await psycopg.AsyncConnection.connect(
            url, connect_timeout=3
        ) as conn:
            await conn.execute("SELECT 1")
    except psycopg.Error:
        return False
    return True


def blob_store_problems() -> Problems:
    """What the ``MERITUM_BLOB_*`` configuration lacks, through core's factory.

    Returns:
        The unset variables, or the blob store as unavailable when building failed.

    Features:
        US-WDR-08, F-30, ADR-31
    """
    try:
        settings = BlobSettings()
    except ValidationError as exc:
        return Problems(
            [f"{ENV_PREFIX}{e['loc'][0]}".upper() for e in exc.errors()], []
        )
    try:
        build_blob_store(settings)
    except BlobError:
        field = BLOB_PROVIDER_FIELDS[settings.provider]
        return Problems([f"{ENV_PREFIX}{field}".upper()], [])
    except Exception:  # ruff: ignore[blind-except] -- any SDK error (e.g. GCS without credentials) means unavailable; the name is enough
        return Problems([], [BLOB_STORE])
    return Problems([], [])


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
    database = partial(database_reachable, settings.database_url)
    return ReadinessProbe(settings, jobs, database, blob_store_problems)
