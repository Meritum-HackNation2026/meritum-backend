"""PostgresRateCounter on a real database (local only, -m integration).

Needs `docker compose up -d --wait db`.
"""

import asyncio
import time
from uuid import uuid4

import psycopg
import pytest

from meritum_backend.constants import LOCAL_DB
from meritum_backend.limits.adapters import PostgresRateCounter


@pytest.mark.integration
def test_two_instances_count_on_one_table() -> None:
    key = f"test:{uuid4().hex}"
    first, second = PostgresRateCounter(LOCAL_DB), PostgresRateCounter(LOCAL_DB)

    async def hits() -> list[int]:
        together = [c.hit(key, 3600) for _ in range(5) for c in (first, second)]
        return sorted(await asyncio.gather(*together))

    assert asyncio.run(hits()) == list(range(1, 11))


@pytest.mark.integration
def test_next_window_starts_from_one() -> None:
    key = f"test:{uuid4().hex}"
    counter = PostgresRateCounter(LOCAL_DB)

    async def hits() -> list[int]:
        first = [await counter.hit(key, 1), await counter.hit(key, 1)]
        await asyncio.sleep(1.1)
        return [*first, await counter.hit(key, 1)]

    while time.time() % 1 > 0.5:  # both first hits in one 1-second window
        time.sleep(0.05)
    assert asyncio.run(hits()) == [1, 2, 1]


@pytest.mark.integration
def test_unreachable_database_lets_the_request_through() -> None:
    counter = PostgresRateCounter("postgresql://x:x@127.0.0.1:1/x")
    assert asyncio.run(counter.hit("k", 60)) == 0


@pytest.mark.integration
def test_finished_windows_leave_the_table() -> None:
    old, new = f"test:{uuid4().hex}", f"test:{uuid4().hex}"
    counter = PostgresRateCounter(LOCAL_DB)

    async def keys_after_window() -> set[str]:
        await counter.hit(old, 1)
        await asyncio.sleep(2.1)  # the prune drops windows older than one window
        await counter.hit(new, 1)
        async with await psycopg.AsyncConnection.connect(LOCAL_DB) as conn:
            cur = await conn.execute(
                "SELECT key FROM rate_limit_hits WHERE key = ANY(%s)", ([old, new],)
            )
            return {row[0] for row in await cur.fetchall()}

    assert asyncio.run(keys_after_window()) == {new}
