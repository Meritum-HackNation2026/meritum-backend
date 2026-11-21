"""Ports of the checks slice: the result cache shared by every channel.

Features:
    US-WTY-03, US-MOD-03, F-05, ADR-19, ADR-22
"""

from datetime import datetime
from typing import Protocol

from meritum_core.checks.contracts import CachedResult


class ResultCache(Protocol):
    """Keeps the substantive part of finished checks by normalised input (port).

    Features:
        US-WTY-03, F-05, ADR-22
    """

    async def lookup(self, key: str, now: datetime) -> CachedResult | None:
        """Read the live entry of an input key.

        Args:
            key: core's ``normalize_input(...).cache_key``.
            now: the request time; an entry past ``expires_at`` is a miss.

        Returns:
            The entry, or None on a miss or when the store is unreachable.
        """
        ...

    async def link(self, check_id: str, key: str) -> None:
        """Remember the input key of a check, so its result can be filled or read.

        Args:
            check_id: the check's id.
            key: its input key.
        """
        ...

    async def fill(self, check_id: str, entry: CachedResult) -> None:
        """Store ``entry`` under the key linked to ``check_id``.

        A live entry stays; an unlinked check stores nothing.

        Args:
            check_id: the finished check.
            entry: its substantive part.
        """
        ...

    async def entry_of(self, check_id: str) -> CachedResult | None:
        """Read the entry under the key linked to ``check_id``, expired or not.

        Args:
            check_id: a check served from the cache.

        Returns:
            The entry, or None when there is none.
        """
        ...
