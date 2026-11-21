"""Builds the check gate from settings.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

from dbos import DBOSClient

from meritum_backend.limits.adapters import (
    DbosPendingChecks,
    MemoryRateCounter,
    PostgresRateCounter,
)
from meritum_backend.limits.gate import CheckGate
from meritum_backend.limits.ports import RateCounter
from meritum_backend.limits.settings import LimitSettings, RateCounterProvider
from meritum_backend.settings import Settings


def build_check_gate(
    settings: Settings, limits: LimitSettings, client: DBOSClient
) -> CheckGate:
    """Build the gate on the counter ``MERITUM_RATE_COUNTER`` names.

    Args:
        settings: the app settings (database URL, environment).
        limits: the limit values and the counter provider.
        client: the DBOS client of the job queue.

    Returns:
        The gate over the shared counter and the DBOS queue.

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
    """
    counter: RateCounter
    match limits.rate_counter:
        case RateCounterProvider.POSTGRES:
            counter = PostgresRateCounter(settings.database_url)
        case RateCounterProvider.MEMORY:
            counter = MemoryRateCounter()
    return CheckGate(counter, DbosPendingChecks(client, settings.env), limits)
