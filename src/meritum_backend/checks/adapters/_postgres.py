"""ResultCache on PostgreSQL tables, shared by every API instance (ADR-22).

Features:
    US-WTY-03, US-MOD-03, F-05, ADR-22
"""

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import LiteralString

import psycopg
from meritum_core.checks.contracts import CachedResult
from psycopg.rows import TupleRow

from meritum_backend.checks.constants import (
    CACHE_CONNECT_TIMEOUT_SECONDS,
    CREATE_CACHE_TABLES,
    ENTRY_OF_CHECK,
    FILL_CACHE,
    LINK_CHECK,
    LOCK_CACHE_TABLES,
    LOOKUP_CACHE,
    PRUNE_ENTRIES,
    PRUNE_LINKS,
)

_log = logging.getLogger(__name__)

type _Params = Mapping[str, object]


class PostgresResultCache:
    """ResultCache over ``result_cache`` and ``result_cache_checks``.

    An unreachable database is a miss: the check then runs the workflow.

    Args:
        conninfo: the API role's database URL.

    Features:
        US-WTY-03, US-MOD-03, F-05, ADR-22
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo
        self._ready = False

    async def lookup(self, key: str, now: datetime) -> CachedResult | None:
        """Read the live entry of ``key`` (see the port).

        Args:
            key: the input key.
            now: the request time.

        Returns:
            The entry, or None on a miss or a database error.
        """
        return await self._entry(LOOKUP_CACHE, {"key": key, "now": now})

    async def link(
        self, check_id: str, key: str, served: CachedResult | None = None
    ) -> None:
        """Remember the key of ``check_id`` (see the port).

        Args:
            check_id: the check's id.
            key: its input key.
            served: for a cache hit, the entry it got.
        """
        snapshot = None if served is None else served.model_dump_json()
        params = {"check_id": check_id, "key": key, "served": snapshot}
        prune = (PRUNE_LINKS, {}), (PRUNE_ENTRIES, {})
        await self._run((LINK_CHECK, params), *prune)

    async def fill(self, check_id: str, entry: CachedResult) -> None:
        """Store ``entry`` under the check's key (see the port).

        Args:
            check_id: the finished check.
            entry: its substantive part.
        """
        params = {
            "check_id": check_id,
            "entry": entry.model_dump_json(),
            "expires_at": entry.expires_at,
            "now": entry.cached_at,
        }
        await self._run((FILL_CACHE, params))

    async def entry_of(self, check_id: str) -> CachedResult | None:
        """Read the entry under the check's key (see the port).

        Args:
            check_id: a check served from the cache.

        Returns:
            The entry, or None.
        """
        return await self._entry(ENTRY_OF_CHECK, {"check_id": check_id})

    async def _entry(
        self, query: LiteralString, params: _Params
    ) -> CachedResult | None:
        rows = await self._run((query, params))
        row = rows[0] if rows else None
        return None if row is None else CachedResult.model_validate(row[0])

    async def _run(self, *statements: tuple[LiteralString, _Params]) -> list[TupleRow]:
        try:
            # shortcut: one connection per call, like the rate counter; add a
            # psycopg_pool pool when check traffic makes connecting a cost.
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CACHE_CONNECT_TIMEOUT_SECONDS
            ) as conn:
                return await self._execute(conn, statements)
        except psycopg.Error:
            _log.warning("result cache unavailable; treated as a miss", exc_info=True)
            return []

    async def _execute(
        self,
        conn: psycopg.AsyncConnection,
        statements: tuple[tuple[LiteralString, _Params], ...],
    ) -> list[TupleRow]:
        await self._ensure_tables(conn)
        rows: list[TupleRow] = []
        for query, params in statements:
            cursor = await conn.execute(query, params)
            has_rows = cursor.description is not None
            rows = await cursor.fetchall() if has_rows else []
        await conn.commit()
        return rows

    async def _ensure_tables(self, conn: psycopg.AsyncConnection) -> None:
        if not self._ready:
            await conn.execute(LOCK_CACHE_TABLES)
            for statement in CREATE_CACHE_TABLES:
                await conn.execute(statement)
            await conn.commit()
            self._ready = True
