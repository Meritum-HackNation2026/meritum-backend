"""Archive store over ``page_archives`` (core migration 0008).

Features:
    US-KOR-07, F-38, ADR-04
"""

import psycopg
from psycopg.rows import dict_row

from meritum_backend.archives.constants import (
    CONNECT_TIMEOUT,
    DELETE_ARCHIVE,
    SELECT_ARCHIVE,
)
from meritum_backend.archives.models import ArchiveRecord


class PostgresArchiveStore:
    """Reads and deletes the rows the worker wrote in the app schema.

    Args:
        conninfo: API database connection string.

    Features:
        US-KOR-07, F-38, ADR-04
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def get(self, archive_id: str) -> ArchiveRecord | None:
        """Return one copy within retention (see ``ArchiveStore.get``).

        Args:
            archive_id: the copy's id.

        Returns:
            The copy, or None.
        """
        async with await psycopg.AsyncConnection.connect(
            self._conninfo, connect_timeout=CONNECT_TIMEOUT
        ) as conn:
            cursor = conn.cursor(row_factory=dict_row)
            await cursor.execute(SELECT_ARCHIVE, (archive_id,))
            row = await cursor.fetchone()
        return None if row is None else ArchiveRecord.model_validate(row)

    async def delete(self, archive_id: str) -> None:
        """Forget one copy (see ``ArchiveStore.delete``).

        Args:
            archive_id: the copy's id.
        """
        async with await psycopg.AsyncConnection.connect(
            self._conninfo, connect_timeout=CONNECT_TIMEOUT
        ) as conn:
            await conn.execute(DELETE_ARCHIVE, (archive_id,))
