"""In-memory jury link storage for local development and tests."""

from datetime import UTC, datetime
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
        """Persist a link and drop the ones already past their deadline.

        Args:
            token_hash: SHA-256 digest of the link token.
            expires_at: the link deadline.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        now = datetime.now(UTC)
        with self._lock:
            self._links = {k: v for k, v in self._links.items() if v > now}
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

    async def peek(self, token_hash: bytes, now: datetime) -> datetime | None:
        """Read the matching link without removing it.

        Args:
            token_hash: SHA-256 digest of the submitted token.
            now: current time used to check validity.

        Returns:
            The expiry of the matching link, or None if missing or expired.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        with self._lock:
            key = next((k for k in self._links if compare_digest(k, token_hash)), None)
            expires_at = None if key is None else self._links[key]
            return expires_at if expires_at is not None and expires_at > now else None

    async def remove(self, token_hash: bytes) -> bool:
        """Delete the matching link.

        Args:
            token_hash: SHA-256 digest of the link token.

        Returns:
            Whether a link was deleted.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        with self._lock:
            return self._links.pop(token_hash, None) is not None
