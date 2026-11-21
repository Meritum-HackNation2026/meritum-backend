"""The admission rule of a new check: rate limits first, then the pending queue.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from functools import cache

from meritum_backend.limits.constants import (
    BUSY,
    CHANNEL_SCOPE,
    EVENTS_SCOPE,
    IP_SCOPE,
    KEY_SECRET_BYTES,
    RATE_LIMITED,
    REGION_SCOPE,
    WINDOW_SECONDS,
)
from meritum_backend.limits.models import Origin, Refusal
from meritum_backend.limits.ports import PendingChecks, RateCounter
from meritum_backend.limits.settings import LimitSettings


@cache
def _process_secret() -> bytes:
    # No MERITUM_CHANNEL_HASH_SALT (local runs, tests): a random key per process,
    # so the keys stay irreversible; instances then count apart.
    return secrets.token_bytes(KEY_SECRET_BYTES)


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
            (self._key(IP_SCOPE, origin.ip), self.limits.checks_per_ip_per_minute),
            (
                self._key(REGION_SCOPE, origin.region),
                self.limits.checks_per_region_per_minute,
            ),
            (
                self._key(CHANNEL_SCOPE, channel),
                self.limits.checks_per_channel_per_minute,
            ),
        )
        for key, limit in limits:
            if await self._over(key, limit):
                return RATE_LIMITED
        most = self.limits.max_pending_checks
        if await self.pending.count(most) >= most:
            return BUSY
        return None

    async def stream_refusal(self, origin: Origin) -> Refusal | None:
        """Count one progress stream and say why it may not open, if it may not.

        Streams have their own per-address budget, so watching a check never
        uses up the budget for starting one.

        Args:
            origin: the client address and region.

        Returns:
            RATE_LIMITED, or None when the stream may open.
        """
        key = self._key(EVENTS_SCOPE, origin.ip)
        if await self._over(key, self.limits.event_streams_per_ip_per_minute):
            return RATE_LIMITED
        return None

    def _key(self, scope: str, value: str) -> str:
        # HMAC with the secret, so the shared table holds no reversible address hash.
        salt = self.limits.channel_hash_salt
        configured = salt.get_secret_value().encode() if salt is not None else b""
        secret = configured or _process_secret()  # an empty secret counts as unset
        message = f"{scope}:{value}".encode()
        return f"{scope}:{hmac.new(secret, message, hashlib.sha256).hexdigest()}"

    async def _over(self, key: str, limit: int) -> bool:
        return await self.counter.hit(key, WINDOW_SECONDS) > limit
