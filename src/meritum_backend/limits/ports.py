"""Ports of the limits slice: the shared rate counter and the pending checks.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23, ADR-18
"""

from typing import Protocol


class RateCounter(Protocol):
    """Fixed-window hit counter shared by every API instance (ADR-18).

    Features:
        US-BEZ-02, F-20, ADR-18
    """

    async def hit(self, key: str, window_seconds: int) -> int:
        """Count one hit of ``key`` in the current window.

        Args:
            key: what is limited, e.g. a hashed client address.
            window_seconds: length of the window; windows align to the epoch.

        Returns:
            Hits of ``key`` in the current window, this one included; 0 when the
            counter is unreachable (the limit then lets the request through).
        """
        ...


class PendingChecks(Protocol):
    """Counts checks waiting in the worker's queue.

    Features:
        US-WDR-03, F-23
    """

    async def count(self, at_most: int) -> int:
        """Count queued and running checks, stopping at ``at_most``.

        Args:
            at_most: the threshold; counting further is not needed.

        Returns:
            The count, at most ``at_most``; 0 when the queue is unreachable.
        """
        ...
