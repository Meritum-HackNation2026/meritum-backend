"""PostgreSQL jury link storage with transactional redemption."""

from datetime import datetime
from secrets import compare_digest

import psycopg
from psycopg.rows import class_row

from meritum_backend.jury.constants import (
    CONNECT_TIMEOUT,
    DELETE_DEMO_LINK,
    DELETE_JURY_LINK,
    GET_JURY_LINK,
    INSERT_DEMO_METADATA,
    INSERT_JURY_LINK,
    LIST_DEMO_LINKS,
    PEEK_JURY_LINK,
    PURGE_EXPIRED_JURY_LINKS,
)
from meritum_backend.jury.ports import DemoLink, JuryUnavailableError


class PostgresJuryLinks:
    """Store links in the app schema shared by all replicas.

    The table comes from core's app migrations (0004), run by the worker.

    Args:
        conninfo: API database connection string.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    async def save(
        self, token_hash: bytes, expires_at: datetime, *, demo: DemoLink | None = None
    ) -> None:
        """Persist the digest and expiry, dropping links past their deadline.

        Args:
            token_hash: SHA-256 digest of the link token.
            expires_at: the link deadline.
            demo: metadata if this is a reusable demo link.

        Raises:
            JuryUnavailableError: the database operation failed.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                await conn.execute(PURGE_EXPIRED_JURY_LINKS)
                await conn.execute(INSERT_JURY_LINK, (token_hash, expires_at))
                if demo is not None:
                    await conn.execute(
                        INSERT_DEMO_METADATA, (token_hash, demo.account, demo.issued_at)
                    )
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
                return await self._consume(conn, token_hash, now)
        except psycopg.Error:
            raise JuryUnavailableError from None

    async def peek(self, token_hash: bytes, now: datetime) -> datetime | None:
        """Read the matching row without locking or deleting it.

        Args:
            token_hash: SHA-256 digest of the submitted token.
            now: current time used to check validity.

        Returns:
            The expiry of the matching link, or None if missing or expired.

        Raises:
            JuryUnavailableError: the database operation failed.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                row = await (
                    await conn.execute(PEEK_JURY_LINK, (token_hash,))
                ).fetchone()
        except psycopg.Error:
            raise JuryUnavailableError from None
        if row is None:
            return None
        if not isinstance(row[0], datetime):
            raise JuryUnavailableError
        return row[0] if row[0] > now else None

    async def remove(self, token_hash: bytes, *, demo_only: bool = False) -> bool:
        """Delete the matching row.

        Args:
            token_hash: SHA-256 digest of the link token.
            demo_only: require a demo metadata record before removing the link.

        Returns:
            Whether a row was deleted.

        Raises:
            JuryUnavailableError: the database operation failed.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._conninfo, connect_timeout=CONNECT_TIMEOUT
            ) as conn:
                query = DELETE_DEMO_LINK if demo_only else DELETE_JURY_LINK
                return (await conn.execute(query, (token_hash,))).rowcount > 0
        except psycopg.Error:
            raise JuryUnavailableError from None

    async def active_demo(self, now: datetime) -> list[DemoLink]:
        """List unexpired demo links, newest first.

        Args:
            now: current time used to check expiry.

        Returns:
            The active demo link metadata.

        Raises:
            JuryUnavailableError: the database operation failed.

        Features:
            US-OBS-06, US-MOD-05, F-28, F-25
        """
        try:
            async with (
                await psycopg.AsyncConnection.connect(
                    self._conninfo, connect_timeout=CONNECT_TIMEOUT
                ) as conn,
                conn.cursor(row_factory=class_row(DemoLink)) as cur,
            ):
                return await (await cur.execute(LIST_DEMO_LINKS, (now,))).fetchall()
        except psycopg.Error:
            raise JuryUnavailableError from None

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
