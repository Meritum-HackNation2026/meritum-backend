"""In-memory archive store: local runs and tests.

Features:
    US-KOR-07, F-38
"""

from datetime import UTC, datetime

from meritum_backend.archives.models import ArchiveRecord


class MemoryArchiveStore:
    """``ArchiveStore`` over a dict; nothing writes it locally but tests.

    Attributes:
        records: the copies by id.

    Features:
        US-KOR-07, F-38
    """

    def __init__(self) -> None:
        self.records: dict[str, ArchiveRecord] = {}

    async def get(self, archive_id: str) -> ArchiveRecord | None:
        """Return one copy within retention (see ``ArchiveStore.get``).

        Args:
            archive_id: the copy's id.

        Returns:
            The copy, or None.
        """
        record = self.records.get(archive_id)
        alive = record is not None and record.expires_at > datetime.now(UTC)
        return record if alive else None

    async def delete(self, archive_id: str) -> None:
        """Forget one copy (see ``ArchiveStore.delete``).

        Args:
            archive_id: the copy's id.
        """
        self.records.pop(archive_id, None)
