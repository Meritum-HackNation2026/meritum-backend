"""Limit settings from MERITUM_* environment variables.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

from enum import StrEnum

from pydantic import PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

from meritum_backend.limits.constants import (
    CHECKS_PER_CHANNEL_PER_MINUTE,
    CHECKS_PER_IP_PER_MINUTE,
    CHECKS_PER_REGION_PER_MINUTE,
    MAX_PENDING_CHECKS,
)


class RateCounterProvider(StrEnum):
    """Where the rate counters live.

    Attributes:
        POSTGRES: a table in the API's database, shared by every instance.
        MEMORY: one process only; for tests and a single local process.

    Features:
        US-BEZ-02, ADR-18
    """

    POSTGRES = "postgres"
    MEMORY = "memory"


class LimitSettings(BaseSettings):
    """Limits of the check intake; defaults are the constants of the slice.

    Attributes:
        checks_per_ip_per_minute: checks one client address may start per minute.
        checks_per_region_per_minute: checks one country may start per minute.
        checks_per_channel_per_minute: checks one channel may start per minute.
        max_pending_checks: queued checks at which new ones are refused.
        rate_counter: where the counters live (MERITUM_RATE_COUNTER).

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
    """

    model_config = SettingsConfigDict(
        env_prefix="MERITUM_", env_file=".env", extra="ignore"
    )

    checks_per_ip_per_minute: PositiveInt = CHECKS_PER_IP_PER_MINUTE
    checks_per_region_per_minute: PositiveInt = CHECKS_PER_REGION_PER_MINUTE
    checks_per_channel_per_minute: PositiveInt = CHECKS_PER_CHANNEL_PER_MINUTE
    max_pending_checks: PositiveInt = MAX_PENDING_CHECKS
    rate_counter: RateCounterProvider = RateCounterProvider.POSTGRES
