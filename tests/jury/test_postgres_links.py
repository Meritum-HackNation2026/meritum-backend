"""PostgresJuryLinks on a real database (local only, -m integration).

Needs `docker compose up -d --wait db` (or MERITUM_TEST_DATABASE_URL); runs as
a role without DDL, like the API on dev (``api_url`` in tests/conftest.py).
"""

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from meritum_backend.jury.adapters import PostgresJuryLinks
from meritum_backend.jury.ports import DemoLink


def _digest() -> bytes:
    return sha256(secrets.token_bytes(32)).digest()


@pytest.mark.integration
def test_concurrent_redemptions_consume_a_link_once(api_url: str) -> None:
    digest, now = _digest(), datetime.now(UTC)
    first, second = PostgresJuryLinks(api_url), PostgresJuryLinks(api_url)

    async def redeem() -> list[datetime | None]:
        await first.save(digest, now + timedelta(hours=1))
        together = [s.consume(digest, now) for _ in range(5) for s in (first, second)]
        return await asyncio.gather(*together)

    assert sum(result is not None for result in asyncio.run(redeem())) == 1


@pytest.mark.integration
def test_expired_link_is_reported_and_not_consumed(api_url: str) -> None:
    digest, now = _digest(), datetime.now(UTC)
    links = PostgresJuryLinks(api_url)

    async def redeem_twice() -> list[datetime | None]:
        await links.save(digest, now - timedelta(seconds=1))
        return [await links.consume(digest, now), await links.consume(digest, now)]

    deadline = now - timedelta(seconds=1)
    assert asyncio.run(redeem_twice()) == [deadline, deadline]


@pytest.mark.integration
def test_issuing_a_link_drops_expired_ones(api_url: str) -> None:
    old, now = _digest(), datetime.now(UTC)
    links = PostgresJuryLinks(api_url)

    async def run() -> datetime | None:
        await links.save(old, now - timedelta(seconds=1))
        await links.save(_digest(), now + timedelta(hours=1))
        return await links.consume(old, now)

    assert asyncio.run(run()) is None


@pytest.mark.integration
def test_demo_metadata_is_shared_and_can_revoke_only_demo_links(api_url: str) -> None:
    digest, jury, now = _digest(), _digest(), datetime.now(UTC)
    expires = now + timedelta(hours=1)
    demo = DemoLink(digest.hex(), "admin", now, expires)
    writer, reader = PostgresJuryLinks(api_url), PostgresJuryLinks(api_url)

    async def run() -> None:
        await writer.save(jury, expires)
        await writer.save(digest, expires, demo=demo)
        assert await reader.active_demo(now) == [demo]
        assert await reader.active_demo(expires) == []
        assert not await reader.remove(jury, demo_only=True)
        assert await reader.remove(digest, demo_only=True)
        assert await writer.peek(digest, now) is None
        assert await writer.active_demo(now) == []
        assert await writer.consume(jury, now) == expires

    asyncio.run(run())
