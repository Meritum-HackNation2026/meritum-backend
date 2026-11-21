"""In-process adapters for tests: a rate counter and a fixed pending queue.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23
"""

from collections.abc import Callable


class MemoryRateCounter:
    """RateCounter in one process's memory, for tests.

    Args:
        clock: seconds since the epoch; frozen by default, so a test never
            straddles a window boundary and sees its count reset.

    Features:
        US-BEZ-02, F-20
    """

    def __init__(self, clock: Callable[[], float] = lambda: 0.0) -> None:
        self._clock = clock
        self._hits: dict[str, tuple[int, int]] = {}

    async def hit(self, key: str, window_seconds: int) -> int:
        """Count one hit of ``key`` in the current window.

        Args:
            key: what is limited.
            window_seconds: length of the window.

        Returns:
            Hits of ``key`` in the current window, this one included.
        """
        window = int(self._clock() // window_seconds)
        # Like the PostgreSQL table: a finished window's keys are gone.
        self._hits = {k: v for k, v in self._hits.items() if v[0] == window}
        hits = self._hits.get(key, (window, 0))[1] + 1
        self._hits[key] = (window, hits)
        return hits

    @property
    def keys(self) -> frozenset[str]:
        """The keys stored now (tests check what the table would hold).

        Returns:
            The keys of the current window.
        """
        return frozenset(self._hits)


class FixedPendingChecks:
    """PendingChecks with a set number of pending checks (tests).

    Args:
        pending: how many checks are pending.

    Features:
        US-WDR-03, F-23
    """

    def __init__(self, pending: int = 0) -> None:
        self._pending = pending

    async def count(self, at_most: int) -> int:
        """Return the set number, capped at ``at_most``.

        Args:
            at_most: the threshold.

        Returns:
            The pending checks, at most ``at_most``.
        """
        return min(self._pending, at_most)
