"""Ports of the health slice: the database and blob store checks of the API.

Features:
    US-WDR-08, F-30
"""

from typing import Protocol

from meritum_backend.health.models import Problems


class DatabaseProbe(Protocol):
    """Checks that the API's database role can run a query.

    Features:
        US-WDR-08, F-30
    """

    async def reachable(self) -> bool:
        """Whether a trivial query succeeded.

        Returns:
            True when the database answered.
        """
        ...


class BlobStoreProbe(Protocol):
    """Checks the blob store configuration of the API.

    Features:
        US-WDR-08, F-30, ADR-31
    """

    def problems(self) -> Problems:
        """What the blob store configuration lacks.

        Returns:
            Unset variable names and unusable providers; both empty when ready.
        """
        ...
