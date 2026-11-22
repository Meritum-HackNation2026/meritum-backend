"""Port of the archive API: the copies' metadata the worker stored.

Features:
    US-KOR-07, F-38
"""

from typing import Protocol

from meritum_backend.archives.models import ArchiveRecord


class ArchiveStore(Protocol):
    """Reads and forgets rows of ``page_archives``.

    Features:
        US-KOR-07, F-38
    """

    async def get(self, archive_id: str) -> ArchiveRecord | None:
        """Return one copy within retention.

        Args:
            archive_id: the copy's id.

        Returns:
            The copy, or None when there is none or it expired.
        """
        ...

    async def delete(self, archive_id: str) -> None:
        """Forget one copy; a missing one is ignored.

        Args:
            archive_id: the copy's id.
        """
        ...
