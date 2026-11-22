"""Source catalogue over the shared ``corpus.documents`` table, read only.

Features:
    US-WDR-06, F-37, ADR-32
"""

from collections.abc import Collection, Mapping
from types import MappingProxyType

import psycopg
from meritum_core.corpus import CorpusUnavailableError

from meritum_backend.mcp.constants import SOURCE_QUERY
from meritum_backend.mcp.ports import SourceInfo


class PostgresSourceCatalogue:
    """SourceCatalogue that only SELECTs from the ``corpus`` schema (ADR-32).

    Args:
        conninfo: libpq connection string of the database with the corpus.

    Features:
        US-WDR-06, F-37, ADR-32
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def describe(self, source_ids: Collection[str]) -> Mapping[str, SourceInfo]:
        """Describe sources.

        Args:
            source_ids: corpus document ids.

        Returns:
            Info per known id. ``corpus.documents`` holds no title yet, so it is None.

        Raises:
            CorpusUnavailableError: PostgreSQL failed.
        """
        if not source_ids:
            return MappingProxyType({})
        try:
            # shortcut: one connection per lookup; pool it when latency matters
            async with await psycopg.AsyncConnection.connect(self._conninfo) as conn:
                cursor = await conn.execute(SOURCE_QUERY, (list(source_ids),))
                rows = await cursor.fetchall()
        except psycopg.Error as exc:
            msg = "corpus.documents lookup failed"
            raise CorpusUnavailableError(msg) from exc
        return {
            source_id: SourceInfo(publisher=publisher_id, url=url)
            for source_id, _domain, publisher_id, url in rows
        }
