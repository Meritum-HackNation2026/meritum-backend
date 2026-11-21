"""DatabaseProbe on PostgreSQL: ``SELECT 1`` with the API's own role.

Features:
    US-WDR-08, F-30
"""

import psycopg

from meritum_backend.health.constants import DATABASE_CONNECT_TIMEOUT_SECONDS


class PostgresProbe:
    """Runs ``SELECT 1`` with the API's database role.

    Args:
        url: the database URL.

    Features:
        US-WDR-08, F-30
    """

    def __init__(self, url: str) -> None:
        self._url = url

    async def reachable(self) -> bool:
        """Whether ``SELECT 1`` succeeded.

        Returns:
            True when the database answered.
        """
        try:
            async with await psycopg.AsyncConnection.connect(
                self._url, connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS
            ) as conn:
                await conn.execute("SELECT 1")
        except psycopg.Error:
            return False
        return True
