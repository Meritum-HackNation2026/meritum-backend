"""ResultCache in one process's memory: tests and behave.

Features:
    US-WTY-03, F-05, ADR-22
"""

from datetime import datetime

from meritum_core.checks.contracts import CachedResult


class MemoryResultCache:
    """ResultCache over two dicts (see the port).

    Features:
        US-WTY-03, F-05, ADR-22
    """

    def __init__(self) -> None:
        self._entries: dict[str, CachedResult] = {}
        self._keys: dict[str, str] = {}

    async def lookup(self, key: str, now: datetime) -> CachedResult | None:
        """Read the live entry of ``key`` (see the port).

        Args:
            key: the input key.
            now: the request time.

        Returns:
            The entry, or None.
        """
        entry = self._entries.get(key)
        return entry if entry is not None and entry.expires_at > now else None

    async def link(self, check_id: str, key: str) -> None:
        """Remember the key of ``check_id`` (see the port).

        Args:
            check_id: the check's id.
            key: its input key.
        """
        self._keys.setdefault(check_id, key)

    async def fill(self, check_id: str, entry: CachedResult) -> None:
        """Store ``entry`` under the check's key (see the port).

        Args:
            check_id: the finished check.
            entry: its substantive part.
        """
        key = self._keys.get(check_id)
        if key is not None and await self.lookup(key, entry.cached_at) is None:
            self._entries[key] = entry

    async def entry_of(self, check_id: str) -> CachedResult | None:
        """Read the entry under the check's key (see the port).

        Args:
            check_id: a check served from the cache.

        Returns:
            The entry, or None.
        """
        key = self._keys.get(check_id)
        return None if key is None else self._entries.get(key)
