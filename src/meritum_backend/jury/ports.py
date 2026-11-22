"""Persistence boundary for one-time jury links."""

from datetime import datetime
from typing import Protocol


class JuryUnavailableError(Exception):
    """The jury link store could not be reached.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """


class JuryLinks(Protocol):
    """Store only hashes and expiry times, and consume each valid hash once.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    async def save(self, token_hash: bytes, expires_at: datetime) -> None:
        """Persist a link.

        Args:
            token_hash: SHA-256 digest of the link token.
            expires_at: the link deadline.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        ...

    async def consume(self, token_hash: bytes, now: datetime) -> datetime | None:
        """Delete the link if it is still valid.

        Args:
            token_hash: SHA-256 digest of the submitted token.
            now: current time used to check validity.

        Returns:
            The expiry of the matching link, or None if missing or already used.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        ...

    async def peek(self, token_hash: bytes, now: datetime) -> datetime | None:
        """Read a link without consuming it (reusable demo links).

        Args:
            token_hash: SHA-256 digest of the submitted token.
            now: current time used to check validity.

        Returns:
            The expiry of the matching link, or None if missing or expired.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        ...

    async def remove(self, token_hash: bytes) -> bool:
        """Delete a link (revocation).

        Args:
            token_hash: SHA-256 digest of the link token.

        Returns:
            Whether a link was deleted.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        ...
