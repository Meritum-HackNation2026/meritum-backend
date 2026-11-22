"""Shared fixtures: a readiness probe on fakes, and an app schema as on dev.

The API role has no DDL in ``app_<env>`` (meritum-infra ``db.sh``): ``api_url``
reproduces that, so an adapter that creates its own tables fails (backend#85).
"""

import os
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import psycopg
import pytest
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import ReadinessReport
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.shared.database.adapters import apply_migrations
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import SecretStr

from meritum_backend.constants import LOCAL_DB
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


@dataclass
class FakeClock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def make_probe() -> MakeProbe:
    def make(  # ruff: ignore[too-many-arguments] -- keyword-only overrides of a test factory
        jobs: InMemoryJobQueue,
        *,
        report: ReadinessReport | None = None,
        settings: Settings | None = None,
        database_ok: bool = True,
        blob: BlobStoreProbe | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> ReadinessProbe:
        probe = ReadinessProbe(
            settings or Settings(channel_hash_salt=SecretStr("salt")),
            jobs,
            FakeDatabase(database_ok),
            blob or FakeBlobStore(),
            clock,
        )
        if report is not None:
            jobs.set_event(probe.workflow_id, READINESS_KEY, report)
        return probe

    return make


API_GRANTS = (
    "GRANT USAGE ON SCHEMA {schema} TO {role}",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {role}",
    "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA {schema} TO {role}",
)


def _run(admin: str, statement: str, **names: str) -> None:
    identifiers = {k: sql.Identifier(v) for k, v in names.items()}
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL(statement).format(**identifiers))  # ty: ignore[invalid-argument-type]  # test-only SQL built from constants


@pytest.fixture
def api_url() -> Iterator[str]:
    """URL of a DML-only role on a freshly migrated schema (its search_path)."""
    admin = os.environ.get("MERITUM_TEST_DATABASE_URL", LOCAL_DB)
    suffix = uuid.uuid4().hex
    schema, role, password = f"app_test_{suffix}", f"api_test_{suffix}", suffix
    _run(admin, "CREATE SCHEMA {schema}", schema=schema)
    apply_migrations(make_conninfo(admin, options=f"-c search_path={schema}"))
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
    for grant in API_GRANTS:
        _run(admin, grant, schema=schema, role=role)
    yield make_conninfo(
        admin,
        user=role,
        password=password,
        dbname=conninfo_to_dict(admin).get("dbname"),
        options=f"-c search_path={schema}",
    )
    _run(admin, "DROP SCHEMA {schema} CASCADE", schema=schema)
    _run(admin, "DROP OWNED BY {role}", role=role)
    _run(admin, "DROP ROLE {role}", role=role)
