"""PostgreSQL notifier configuration: one row in the API schema.

Features:
    US-POW-05, US-MOD-01, F-26
"""

import psycopg
from pydantic import SecretStr

from meritum_backend.notifications.constants import (
    CONNECT_TIMEOUT,
    CREATE_CONFIG_TABLE,
    DELETE_CONFIG,
    GET_CONFIG,
    LOCK_CONFIG_SCHEMA,
    UPSERT_CONFIG,
)
from meritum_backend.notifications.models import NotifierConfig


class PostgresNotifierConfigStore:
    """Stores the target where every API replica reads it.

    The secret sits in the table as plain text, like the other settings of the
    API schema; the API never returns it.

    Args:
        conninfo: API database connection string.

    Features:
        US-POW-05, US-MOD-01, F-26
    """

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo
        self._ready = False

    async def _connect(self) -> psycopg.AsyncConnection:
        conn = await psycopg.AsyncConnection.connect(
            self._conninfo, connect_timeout=CONNECT_TIMEOUT
        )
        if not self._ready:
            await conn.execute(LOCK_CONFIG_SCHEMA)
            await conn.execute(CREATE_CONFIG_TABLE)
            await conn.commit()
            self._ready = True
        return conn

    async def get(self) -> NotifierConfig | None:
        """Read the target.

        Returns:
            The configuration, or None.
        """
        async with await self._connect() as conn:
            row = await (await conn.execute(GET_CONFIG)).fetchone()
        if row is None:
            return None
        kind, url, secret = row
        return NotifierConfig(
            kind=kind, url=url, secret=None if secret is None else SecretStr(secret)
        )

    async def save(self, config: NotifierConfig) -> None:
        """Replace the target.

        Args:
            config: the new configuration.
        """
        secret = None if config.secret is None else config.secret.get_secret_value()
        async with await self._connect() as conn:
            await conn.execute(UPSERT_CONFIG, (config.kind, config.url, secret))

    async def delete(self) -> None:
        """Remove the target."""
        async with await self._connect() as conn:
            await conn.execute(DELETE_CONFIG)
