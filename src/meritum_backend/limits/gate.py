"""The admission rule of a new check: rate limits first, then the pending queue.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

import hashlib
from dataclasses import dataclass

from meritum_backend.limits.constants import BUSY, RATE_LIMITED, WINDOW_SECONDS
from meritum_backend.limits.models import Refusal
from meritum_backend.limits.ports import PendingChecks, RateCounter
from meritum_backend.limits.settings import LimitSettings


@dataclass(frozen=True)
class Origin:
    """Where a request comes from.

    Attributes:
        ip: the client address (from uvicorn --proxy-headers).
        region: ISO 3166 country code from Cloudflare, or ``XX``.

    Features:
        US-BEZ-02, F-20
    """

    ip: str
    region: str


def _key(scope: str, value: str) -> str:
    # Hashed, so the shared table never stores a client address in clear.
    return f"{scope}:{hashlib.sha256(value.encode()).hexdigest()}"


@dataclass(frozen=True)
class CheckGate:
    """Decides whether a new check may start.

    Attributes:
        counter: the shared rate counter.
        pending: the pending checks of the worker's queue.
        limits: the limit values.

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
    """

    counter: RateCounter
    pending: PendingChecks
    limits: LimitSettings

    async def refusal(self, origin: Origin, channel: str) -> Refusal | None:
        """Count the check and say why it may not start, if it may not.

        Args:
            origin: the client address and region.
            channel: the channel of the check.

        Returns:
            RATE_LIMITED or BUSY, or None when the check may start.
        """
        limits = (
            (_key("ip", origin.ip), self.limits.checks_per_ip_per_minute),
            (_key("region", origin.region), self.limits.checks_per_region_per_minute),
            (_key("channel", channel), self.limits.checks_per_channel_per_minute),
        )
        for key, limit in limits:
            if await self.counter.hit(key, WINDOW_SECONDS) > limit:
                return RATE_LIMITED
        most = self.limits.max_pending_checks
        if await self.pending.count(most) >= most:
            return BUSY
        return None
