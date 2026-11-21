"""PostgresRateCounter on a real database (local only, -m integration).

Needs `docker compose up -d --wait db`.
"""

import asyncio
from uuid import uuid4

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


def test_unreachable_database_lets_the_request_through() -> None:
    counter = PostgresRateCounter("postgresql://x:x@127.0.0.1:1/x")
    assert asyncio.run(counter.hit("k", 60)) == 0
