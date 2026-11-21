"""MemoryJuryLinks: the local store behaves like the PostgreSQL one."""

import asyncio
from datetime import UTC, datetime, timedelta

from meritum_backend.jury.adapters import MemoryJuryLinks


def test_issuing_a_link_drops_expired_ones() -> None:
    links, now = MemoryJuryLinks(), datetime.now(UTC)

    async def run() -> datetime | None:
        await links.save(b"old", now - timedelta(seconds=1))
        await links.save(b"new", now + timedelta(hours=1))
        return await links.consume(b"old", now)

    assert asyncio.run(run()) is None
