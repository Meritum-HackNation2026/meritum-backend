"""Persistence boundary for one-time jury links."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

type DemoAccount = Literal["obywatel", "admin"]


@dataclass(frozen=True)
class DemoLink:
    """Metadata of a demo link, suitable for listing without its URL.

    Attributes:
        id: hex digest used only to identify a link for management.
        account: technical account opened by the link.
        issued_at: when the administrator issued it.
        expires_at: link deadline.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    id: str
    account: DemoAccount
    issued_at: datetime
    expires_at: datetime


class JuryUnavailableError(Exception):
    """The jury link store could not be reached.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """


class JuryLinks(Protocol):
    """Store link digests, expiry times and metadata for reusable demo links.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    async def save(
        self, token_hash: bytes, expires_at: datetime, *, demo: DemoLink | None = None
    ) -> None:
        """Persist a link.

        Args:
            token_hash: SHA-256 digest of the link token.
            expires_at: the link deadline.
            demo: metadata if this is a reusable demo link.

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

    async def remove(self, token_hash: bytes, *, demo_only: bool = False) -> bool:
        """Delete a link (revocation).

        Args:
            token_hash: SHA-256 digest of the link token.
            demo_only: require a demo metadata record before removing the link.

        Returns:
            Whether a link was deleted.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        ...

    async def active_demo(self, now: datetime) -> list[DemoLink]:
        """List unexpired demo links, newest first.

        Args:
            now: current time used to check expiry.

        Returns:
            The active demo link metadata.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        ...
