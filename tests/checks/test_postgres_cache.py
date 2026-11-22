"""PostgresResultCache on a real database (local only, -m integration).

Needs `docker compose up -d --wait db`.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from meritum_backend.checks.adapters import PostgresResultCache
from meritum_backend.checks.cache import cache_entry
from meritum_backend.constants import LOCAL_DB

from .cache_fakes import RESULT


@pytest.mark.integration
def test_two_instances_share_one_entry_until_it_expires() -> None:
    now = datetime.now(UTC)
    key, first_id, hit_id = uuid4().hex, uuid4().hex, uuid4().hex
    entry = cache_entry(RESULT, now)
    assert entry is not None
    writer, reader = PostgresResultCache(LOCAL_DB), PostgresResultCache(LOCAL_DB)

    async def scenario() -> None:
        await writer.link(first_id, key)
        await writer.fill(first_id, entry)
        assert await reader.lookup(key, now) == entry
        await reader.link(hit_id, key, entry)
        assert await reader.entry_of(hit_id) == entry
        assert await reader.lookup(key, now + timedelta(hours=2)) is None

    asyncio.run(scenario())


def test_an_unreachable_database_is_a_miss() -> None:
    cache = PostgresResultCache("postgresql://x:x@127.0.0.1:1/x")
    assert asyncio.run(cache.lookup("key", datetime.now(UTC))) is None


def test_an_entry_stored_before_the_ai_marker_is_a_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = cache_entry(RESULT, datetime.now(UTC))
    assert entry is not None
    old = entry.model_dump(mode="json", exclude={"ai_marker"})

    async def stored(*_: object) -> list[tuple[object]]:  # ruff: ignore[unused-async] -- stands in for the async _run
        return [(old,)]

    monkeypatch.setattr(PostgresResultCache, "_run", stored)
    cache = PostgresResultCache(LOCAL_DB)
    assert asyncio.run(cache.lookup("key", datetime.now(UTC))) is None
    assert asyncio.run(cache.entry_of("chk-old")) is None
