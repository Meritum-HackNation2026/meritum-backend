"""In-memory jury link storage for local development and tests."""

from datetime import UTC, datetime
from secrets import compare_digest
from threading import Lock

from meritum_backend.jury.ports import DemoLink


class MemoryJuryLinks:
    """Store links in this process, with atomic consumption.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    def __init__(self) -> None:
        self._links: dict[bytes, datetime] = {}
        self._demo: dict[bytes, DemoLink] = {}
        self._lock = Lock()

    async def save(
        self, token_hash: bytes, expires_at: datetime, *, demo: DemoLink | None = None
    ) -> None:
        """Persist a link and drop the ones already past their deadline.

        Args:
            token_hash: SHA-256 digest of the link token.
            expires_at: the link deadline.
            demo: metadata if this is a reusable demo link.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        now = datetime.now(UTC)
        with self._lock:
            self._links = {k: v for k, v in self._links.items() if v > now}
            self._demo = {
                key: link for key, link in self._demo.items() if key in self._links
            }
            self._links[token_hash] = expires_at
            if demo is not None:
                self._demo[token_hash] = demo

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
                self._demo.pop(key, None)
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

    async def remove(self, token_hash: bytes, *, demo_only: bool = False) -> bool:
        """Delete the matching link.

        Args:
            token_hash: SHA-256 digest of the link token.
            demo_only: require a demo metadata record before removing the link.

        Returns:
            Whether a link was deleted.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        with self._lock:
            if demo_only and token_hash not in self._demo:
                return False
            self._demo.pop(token_hash, None)
            return self._links.pop(token_hash, None) is not None

    async def active_demo(self, now: datetime) -> list[DemoLink]:
        """List unexpired demo links, newest first.

        Args:
            now: current time used to check expiry.

        Returns:
            The active demo link metadata.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        with self._lock:
            return sorted(
                (link for link in self._demo.values() if link.expires_at > now),
                key=lambda link: (link.issued_at, link.id),
                reverse=True,
            )
