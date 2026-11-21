"""PostgreSQL jury link storage with transactional redemption."""

from datetime import datetime
from secrets import compare_digest

import psycopg

from meritum_backend.jury.constants import (
    CONNECT_TIMEOUT,
    CREATE_JURY_TABLE,
    DELETE_JURY_LINK,
    GET_JURY_LINK,
    INSERT_JURY_LINK,
    LOCK_JURY_SCHEMA,
    PURGE_EXPIRED_JURY_LINKS,
)
from meritum_backend.jury.ports import JuryUnavailableError


class PostgresJuryLinks:
    """Store links in the API schema shared by all replicas.

    Args:
        conninfo: API database connection string.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo
        self._ready = False

    async def save(self, token_hash: bytes, expires_at: datetime) -> None:
        """Persist the digest and expiry, dropping links past their deadline.

        Args:
            token_hash: SHA-256 digest of the link token.
            expires_at: the link deadline.

        Raises:
            JuryUnavailableError: the database operation failed.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                await self._ensure_table(conn)
                await conn.execute(PURGE_EXPIRED_JURY_LINKS)
                await conn.execute(INSERT_JURY_LINK, (token_hash, expires_at))
        except psycopg.Error:
            raise JuryUnavailableError from None

    async def consume(self, token_hash: bytes, now: datetime) -> datetime | None:
        """Lock the matching row so concurrent requests cannot both redeem it.

        Args:
            token_hash: SHA-256 digest of the submitted token.
            now: current time used to check validity.

        Returns:
            The expiry of the matching link, or None if missing or already used.

        Raises:
            JuryUnavailableError: the database operation failed.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                await self._ensure_table(conn)
                return await self._consume(conn, token_hash, now)
        except psycopg.Error:
            raise JuryUnavailableError from None

    async def _ensure_table(self, conn: psycopg.AsyncConnection) -> None:
        if not self._ready:
            await conn.execute(LOCK_JURY_SCHEMA)
            await conn.execute(CREATE_JURY_TABLE)
            await conn.commit()
            self._ready = True

    @staticmethod
    async def _consume(
        conn: psycopg.AsyncConnection, token_hash: bytes, now: datetime
    ) -> datetime | None:
        row = await (await conn.execute(GET_JURY_LINK, (token_hash,))).fetchone()
        if row is None or not compare_digest(row[0], token_hash):
            return None
        expires_at = row[1]
        if not isinstance(expires_at, datetime):
            raise JuryUnavailableError
        if expires_at > now:
            await conn.execute(DELETE_JURY_LINK, (token_hash,))
        return expires_at
