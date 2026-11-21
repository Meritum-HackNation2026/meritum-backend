"""Shared fixtures: a readiness probe on fakes, ready unless a test says otherwise."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import ReadinessReport
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr

from meritum_backend.health.readiness import Problems, ReadinessProbe
from meritum_backend.settings import Settings

type MakeProbe = Callable[..., ReadinessProbe]


def worker_report(missing: list[str] | None = None) -> ReadinessReport:
    return ReadinessReport(
        missing_env=missing or [],
        unavailable_providers=[],
        checked_at=datetime.now(UTC),
    )


@pytest.fixture
def make_probe() -> MakeProbe:
    def make(
        jobs: InMemoryJobQueue,
        *,
        report: ReadinessReport | None = None,
        settings: Settings | None = None,
        database_ok: bool = True,
        blob: Problems | None = None,
    ) -> ReadinessProbe:
        async def database() -> bool:  # ruff: ignore[unused-async] -- the probe awaits it
            return database_ok

        probe = ReadinessProbe(
            settings or Settings(channel_hash_salt=SecretStr("salt")),
            jobs,
            database,
            lambda: blob or Problems([], []),
        )
        if report is not None:
            jobs.set_event(probe.workflow_id, READINESS_KEY, report)
        return probe

    return make
