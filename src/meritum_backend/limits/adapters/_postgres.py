"""RateCounter on a PostgreSQL table, shared by every API instance (ADR-18).

Features:
    US-BEZ-02, F-20, ADR-18
"""

import logging

import psycopg

from meritum_backend.limits.constants import (
    CONNECT_TIMEOUT_SECONDS,
    HIT_RATE_KEY,
    PRUNE_RATE_WINDOWS,
)

_log = logging.getLogger(__name__)


class PostgresRateCounter:
    """RateCounter over the ``rate_limit_hits`` table.

    The table comes from core's app migrations (0004), run by the worker.

    Args:
        conninfo: the API role's database URL.

    Features:
        US-BEZ-02, F-20, ADR-18
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def hit(self, key: str, window_seconds: int) -> int:
        """Count one hit of ``key`` in the current window.

        Args:
            key: what is limited (a hashed value).
            window_seconds: length of the window.

        Returns:
            Hits in the current window, this one included; 0 when the database
            is unreachable (Cloudflare's limits still stand in front of the API).
        """
        try:
            # shortcut: one connection per hit; add a psycopg_pool pool when
            # check traffic makes connecting show up in latency.
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT_SECONDS
            ) as conn:
                return await self._count(conn, key, window_seconds)
        except psycopg.Error:
            _log.warning("rate counter unavailable; request let through", exc_info=True)
            return 0

    async def forget_finished(self, window_seconds: int) -> None:
        """Delete the rows of finished windows (the API runs it periodically).

        Args:
            window_seconds: length of the window.
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT_SECONDS
            ) as conn:
                await conn.execute(PRUNE_RATE_WINDOWS, {"window": window_seconds})
        except psycopg.Error:
            _log.warning("rate counter unavailable; old windows stay", exc_info=True)

    @staticmethod
    async def _count(
        conn: psycopg.AsyncConnection, key: str, window_seconds: int
    ) -> int:
        params = {"key": key, "window": window_seconds}
        row = await (await conn.execute(HIT_RATE_KEY, params)).fetchone()
        await conn.commit()  # the hit holds no row lock while old windows go
        await conn.execute(PRUNE_RATE_WINDOWS, params)
        return int(row[0]) if row is not None else 0
