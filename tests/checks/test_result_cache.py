"""POST /api/v1/checks with the result cache: one answer for every channel."""

import asyncio
from datetime import UTC, datetime, timedelta
from itertools import starmap

import pytest
from fastapi.testclient import TestClient
from meritum_core.checks import CheckResult, Escalation
from meritum_core.checks.contracts import CachedResult
from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.jobs.contracts import EscalateClaimInput
from pydantic import SecretStr, ValidationError

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_records, get_result_cache
from meritum_backend.checks.cache import cache_entry
from meritum_backend.checks.constants import SESSION_HEADER, SUBSTANTIVE_FIELDS
from meritum_backend.settings import Settings

from .cache_fakes import CASE, FAILURE, RESULT, FinishedWorker
from .conftest import OFFLINE_DB, MakeClient

TEXT = 'Czy "Wrocław" był jedynym miastem, gdzie 65-latkowie jeździli za darmo?'
SPACED = "  Czy  „Wrocław” był jedynym miastem,  gdzie 65-latkowie jeździli za darmo? "
NOW = datetime(2026, 11, 21, 12, tzinfo=UTC)


class Channels:
    def __init__(self, make_client: MakeClient, worker: FinishedWorker) -> None:
        self.records = InMemoryCheckRecordRepository()
        self.cache = MemoryResultCache()
        salt = SecretStr("test-salt")
        settings = Settings(database_url=OFFLINE_DB, channel_hash_salt=salt)
        self.client: TestClient = make_client(worker, settings)
        overrides = self.client.app.dependency_overrides  # ty: ignore[missing-attribute]  # TestClient.app is the FastAPI app
        overrides[get_records] = lambda: self.records
        overrides[get_result_cache] = lambda: self.cache

    def check(
        self, channel: str, text: str, session: str = "session-0123456789"
    ) -> CheckResult:
        body = {"channel": channel, "text": text}
        if channel == "discord":
            body["channel_user_id"] = "1234567890"
        headers = {SESSION_HEADER: session}
        posted = self.client.post("/api/v1/checks", json=body, headers=headers)
        assert posted.status_code == 202, posted.text
        polled = self.client.get(f"/api/v1/checks/{posted.json()['check_id']}")
        return CheckResult.model_validate(polled.json()["result"])


def _substance(result: CheckResult) -> str:
    return result.model_dump_json(include=set(SUBSTANTIVE_FIELDS))


def test_every_channel_gets_the_same_substance_and_one_workflow(
    make_client: MakeClient,
) -> None:
    worker = FinishedWorker()
    channels = Channels(make_client, worker)
    results = list(
        starmap(
            channels.check,
            (
                ("web", TEXT),
                ("extension", SPACED),
                ("discord", TEXT.replace('"', "«", 1).replace('"', "»")),
            ),
        )
    )
    assert len({_substance(r) for r in results}) == 1
    assert len(worker.checks()) == 1
    hits = [r.check_id for r in results[1:]]
    for check_id in hits:
        record = channels.records._records[check_id]  # ruff: ignore[private-member-access]  # the fake has no list-all
        assert record.cache_hit


def test_a_technical_failure_is_never_cached(make_client: MakeClient) -> None:
    worker = FinishedWorker(FAILURE)
    channels = Channels(make_client, worker)
    channels.check("web", TEXT)
    channels.check("web", TEXT)
    assert len(worker.checks()) == 2


def test_a_hit_gets_its_own_escalation_never_the_cached_case(
    make_client: MakeClient,
) -> None:
    worker = FinishedWorker(first_case=Escalation(state="created", case_id="#S-7"))
    channels = Channels(make_client, worker)
    first = channels.check("web", TEXT, "session-aaaaaaaaaa")
    hit = channels.check("extension", TEXT, "session-bbbbbbbbbb")
    assert first.escalation is not None
    assert first.escalation.case_id == "#S-7"
    assert hit.escalation == CASE
    escalations = [
        j.payload for j in worker.enqueued if j.spec.name == "escalate_claim"
    ]
    assert escalations == [
        EscalateClaimInput(check_id=hit.check_id, claim_index=0, reason="cache_hit")
    ]


def test_cache_entry_keeps_only_cacheable_results() -> None:
    assert cache_entry(FAILURE, NOW) is None
    entry = cache_entry(RESULT, NOW)
    assert entry is not None
    assert entry.expires_at - entry.cached_at == timedelta(hours=2)
    with pytest.raises(ValidationError):
        CachedResult.model_validate(
            {**entry.model_dump(), "status": "technical_failure"}
        )


def test_an_expired_entry_is_a_miss() -> None:
    asyncio.run(_expiry())


async def _expiry() -> None:
    cache = MemoryResultCache()
    entry = cache_entry(RESULT, NOW)
    assert entry is not None
    await cache.link("chk-1", "key")
    await cache.fill("chk-1", entry)
    assert await cache.lookup("key", NOW + timedelta(hours=1)) == entry
    assert await cache.lookup("key", NOW + timedelta(hours=2)) is None
