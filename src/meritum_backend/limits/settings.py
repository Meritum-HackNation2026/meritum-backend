"""Limit settings from MERITUM_* environment variables.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from meritum_backend.limits.constants import (
    CHECKS_PER_CHANNEL_PER_MINUTE,
    CHECKS_PER_IP_PER_MINUTE,
    CHECKS_PER_REGION_PER_MINUTE,
    EVENT_STREAMS_PER_IP_PER_MINUTE,
    MAX_PENDING_CHECKS,
)


class LimitSettings(BaseSettings):
    """Limits of the check intake; defaults are the constants of the slice.

    Attributes:
        checks_per_ip_per_minute: checks one client address may start per minute.
        checks_per_region_per_minute: checks one country may start per minute.
        checks_per_channel_per_minute: checks one channel may start per minute.
        event_streams_per_ip_per_minute: progress streams one client address
            may open per minute.
        max_pending_checks: queued checks at which new ones are refused.
        channel_hash_salt: HMAC key of the counter keys, the same secret as the
            channel user id hash (MERITUM_CHANNEL_HASH_SALT, backend#24); a
            random key per process when unset.

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
    """

    model_config = SettingsConfigDict(
        env_prefix="MERITUM_", env_file=".env", extra="ignore"
    )

    checks_per_ip_per_minute: PositiveInt = CHECKS_PER_IP_PER_MINUTE
    checks_per_region_per_minute: PositiveInt = CHECKS_PER_REGION_PER_MINUTE
    checks_per_channel_per_minute: PositiveInt = CHECKS_PER_CHANNEL_PER_MINUTE
    event_streams_per_ip_per_minute: PositiveInt = EVENT_STREAMS_PER_IP_PER_MINUTE
    max_pending_checks: PositiveInt = MAX_PENDING_CHECKS
    channel_hash_salt: SecretStr | None = None
