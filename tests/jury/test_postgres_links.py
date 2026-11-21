"""PostgresJuryLinks on a real database (local only, -m integration).

Needs `docker compose up -d --wait db`.
"""

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from meritum_backend.constants import LOCAL_DB
from meritum_backend.jury.adapters import PostgresJuryLinks


def _digest() -> bytes:
    return sha256(secrets.token_bytes(32)).digest()


@pytest.mark.integration
def test_concurrent_redemptions_consume_a_link_once() -> None:
    digest, now = _digest(), datetime.now(UTC)
    first, second = PostgresJuryLinks(LOCAL_DB), PostgresJuryLinks(LOCAL_DB)

    async def redeem() -> list[datetime | None]:
        await first.save(digest, now + timedelta(hours=1))
        together = [s.consume(digest, now) for _ in range(5) for s in (first, second)]
        return await asyncio.gather(*together)

    assert sum(result is not None for result in asyncio.run(redeem())) == 1


@pytest.mark.integration
def test_expired_link_is_reported_and_not_consumed() -> None:
    digest, now = _digest(), datetime.now(UTC)
    links = PostgresJuryLinks(LOCAL_DB)

    async def redeem_twice() -> list[datetime | None]:
        await links.save(digest, now - timedelta(seconds=1))
        return [await links.consume(digest, now), await links.consume(digest, now)]

    deadline = now - timedelta(seconds=1)
    assert asyncio.run(redeem_twice()) == [deadline, deadline]
