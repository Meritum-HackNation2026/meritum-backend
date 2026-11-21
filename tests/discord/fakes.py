"""Fakes of the Discord tests: the app on in-memory ports and a recording client."""

from typing import override

from fastapi.testclient import TestClient
from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from pydantic import SecretStr
from tests.checks.cache_fakes import FinishedWorker
from tests.checks.conftest import OFFLINE_DB
from tests.conftest import MakeProbe, worker_report

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_records, get_result_cache
from meritum_backend.discord.api import get_replies
from meritum_backend.health.api import get_readiness
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings


class FakeReplies:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def edit_original(self, application_id: str, token: str, text: str) -> None:
        self.sent.append(("edit", f"{application_id}/{token}", text))

    async def follow_up(self, application_id: str, token: str, text: str) -> None:
        self.sent.append(("follow_up", f"{application_id}/{token}", text))


def make_client(
    public_key: str | None,
    make_probe: MakeProbe,
    jobs: InMemoryJobQueue | None = None,
    replies: FakeReplies | None = None,
    records: InMemoryCheckRecordRepository | None = None,
) -> TestClient:
    settings = Settings(
        discord_public_key=public_key,
        channel_hash_salt=SecretStr("salt"),
        database_url=OFFLINE_DB,
    )
    app = create_app(settings)
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    cache = MemoryResultCache()
    records = records or InMemoryCheckRecordRepository()
    probe = make_probe(InMemoryJobQueue(), report=worker_report())
    app.dependency_overrides |= {
        get_settings: lambda: settings,
        get_jobs: lambda: jobs or FinishedWorker(),
        get_check_gate: lambda: gate,
        get_result_cache: lambda: cache,
        get_records: lambda: records,
        get_readiness: lambda: probe,
        get_replies: lambda: replies or FakeReplies(),
    }
    return TestClient(app)


class FailedWorker(FinishedWorker):
    @override
    async def state(self, workflow_id: str) -> JobState | None:
        known = await super().state(workflow_id)
        if known is None:
            return None
        return JobState(workflow_id=workflow_id, status="ERROR", output=None)
