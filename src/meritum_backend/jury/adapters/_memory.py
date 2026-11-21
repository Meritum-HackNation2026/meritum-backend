"""In-memory jury link storage for local development and tests."""

from datetime import datetime
from secrets import compare_digest
from threading import Lock


class MemoryJuryLinks:
    """Store links in this process, with atomic consumption.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    def __init__(self) -> None:
        self._links: dict[bytes, datetime] = {}
        self._lock = Lock()

    async def save(self, token_hash: bytes, expires_at: datetime) -> None:
        """Persist a link.

        Args:
            token_hash: SHA-256 digest of the link token.
            expires_at: the link deadline.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        with self._lock:
            self._links[token_hash] = expires_at

    async def consume(self, token_hash: bytes, now: datetime) -> datetime | None:
        """Remove the matching link if still valid.

        Args:
            token_hash: SHA-256 digest of the submitted token.
            now: current time used to check validity.

        Returns:
            The expiry of the matching link, or None if missing or already used.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        with self._lock:
            key = next((k for k in self._links if compare_digest(k, token_hash)), None)
            if key is None:
                return None
            expires_at = self._links[key]
            if expires_at > now:
                del self._links[key]
            return expires_at
