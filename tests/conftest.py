"""Shared fixtures: a readiness probe on fakes, ready unless a test says otherwise."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import ReadinessReport
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr

from meritum_backend.health.models import Problems
from meritum_backend.health.ports import BlobStoreProbe
from meritum_backend.health.readiness import ReadinessProbe
from meritum_backend.settings import Settings

type MakeProbe = Callable[..., ReadinessProbe]


def worker_report(missing: list[str] | None = None) -> ReadinessReport:
    return ReadinessReport(
        missing_env=missing or [],
        unavailable_providers=[],
        checked_at=datetime.now(UTC),
    )


@dataclass
class FakeDatabase:
    ok: bool = True

    async def reachable(self) -> bool:
        return self.ok


@dataclass
class FakeBlobStore:
    found: Problems = field(default_factory=lambda: Problems([], []))

    def problems(self) -> Problems:
        return self.found


@pytest.fixture
def make_probe() -> MakeProbe:
    def make(
        jobs: InMemoryJobQueue,
        *,
        report: ReadinessReport | None = None,
        settings: Settings | None = None,
        database_ok: bool = True,
        blob: BlobStoreProbe | None = None,
    ) -> ReadinessProbe:
        probe = ReadinessProbe(
            settings or Settings(channel_hash_salt=SecretStr("salt")),
            jobs,
            FakeDatabase(database_ok),
            blob or FakeBlobStore(),
        )
        if report is not None:
            jobs.set_event(probe.workflow_id, READINESS_KEY, report)
        return probe

    return make
