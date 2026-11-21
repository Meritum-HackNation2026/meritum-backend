"""Builds the check gate from settings.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

import logging

from dbos import DBOSClient

from meritum_backend.limits.adapters import DbosPendingChecks, PostgresRateCounter
from meritum_backend.limits.gate import CheckGate
from meritum_backend.limits.settings import LimitSettings
from meritum_backend.settings import Settings

_log = logging.getLogger(__name__)


def build_check_gate(
    settings: Settings, limits: LimitSettings, client: DBOSClient
) -> CheckGate:
    """Build the gate on the shared PostgreSQL counter and the DBOS queue.

    Args:
        settings: the app settings (database URL, environment).
        limits: the limit values.
        client: the DBOS client of the job queue.

    Returns:
        The gate over the shared counter and the DBOS queue.

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
    """
    if limits.channel_hash_salt is None:
        _log.warning("MERITUM_CHANNEL_HASH_SALT unset: per-process counter keys")
    counter = PostgresRateCounter(settings.database_url)
    return CheckGate(counter, DbosPendingChecks(client, settings.env), limits)
