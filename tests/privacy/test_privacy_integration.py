"""Deletion on real PostgreSQL: no app table keeps the session (local only).

Run with ``uv run pytest -m integration tests/privacy``. Needs
``MERITUM_TEST_DATABASE_URL`` (a PostgreSQL the user may create schemas in) and
the DBOS system tables in ``worker_local`` of the same database: start the worker
once, or run ``uv run dbos migrate -s "$URL" --schema worker_local``. The DBOS
rows go when the worker runs ``delete_subject`` (worker/024): with the worker
running on the same database, ``MERITUM_TEST_WORKER=1`` also checks that no DBOS
row names the session; without it that test stops after the enqueue.
"""

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from dbos import DBOSClient
from meritum_core.checks import CheckRequest
from meritum_core.jobs.adapters import DbosJobQueue
from meritum_core.jobs.contracts import (
    APPLICATION_NAME,
    CHECK,
    DELETE_SUBJECT,
    CheckInput,
)
from meritum_core.observability import build_app_repositories
from meritum_core.shared.database import DatabaseProvider, DatabaseSettings
from meritum_core.shared.database.adapters import apply_migrations
from psycopg import sql
from psycopg.conninfo import make_conninfo

from meritum_backend.privacy import delete_subject

from .conftest import ALL, SESSION, Remaining, Seed

APP_TABLES = ("check_records", "moderator_cases", "notifications")
DBOS_SCHEMA = "worker_local"
WORKER_WAIT_SECONDS = 60


@pytest.fixture
def admin_url() -> str:
    url = os.environ.get("MERITUM_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("set MERITUM_TEST_DATABASE_URL to a local PostgreSQL")
    return url


@pytest.fixture
def app_url(admin_url: str) -> Iterator[str]:
    schema = f"test_{uuid.uuid4().hex}"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_conninfo(admin_url, options=f"-c search_path={schema}")
    apply_migrations(url)
    yield url
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def rows_naming(url: str, value: str, tables: list[sql.Identifier]) -> int:
    with psycopg.connect(url) as conn:
        return sum(
            conn.execute(
                sql.SQL("SELECT count(*) FROM {} t WHERE t::text LIKE %s").format(
                    table
                ),
                (f"%{value}%",),
            ).fetchone()[0]  # ty: ignore[not-subscriptable]  # count(*) returns one row
            for table in tables
        )


def app_rows(url: str, value: str) -> int:
    return rows_naming(url, value, [sql.Identifier(t) for t in APP_TABLES])


def dbos_rows(url: str, value: str) -> int:
    with psycopg.connect(url) as conn:
        names = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            (DBOS_SCHEMA,),
        ).fetchall()
    return rows_naming(url, value, [sql.Identifier(DBOS_SCHEMA, n) for (n,) in names])


@pytest.fixture
def dbos(admin_url: str) -> Iterator[DBOSClient]:
    client = DBOSClient(
        system_database_url=admin_url,
        dbos_system_schema=DBOS_SCHEMA,
        application_name=APPLICATION_NAME,
    )
    yield client
    client.destroy()


@pytest.mark.integration
def test_no_app_table_names_the_session_after_deletion(
    app_url: str, dbos: DBOSClient, seed: Seed, remaining: Remaining
) -> None:
    settings = DatabaseSettings(provider=DatabaseProvider.POSTGRES, url=app_url)
    repos = build_app_repositories(settings)
    seed(repos)
    assert app_rows(app_url, SESSION) > 0
    before = len(dbos.list_workflows(name=DELETE_SUBJECT.name))
    jobs = DbosJobQueue(dbos, app_version="local")
    asyncio.run(delete_subject("session_id", SESSION, repos.eraser, jobs))
    assert app_rows(app_url, SESSION) == 0
    assert remaining(repos) == ALL - {"c_s"}
    assert len(dbos.list_workflows(name=DELETE_SUBJECT.name)) == before + 1


@pytest.mark.integration
def test_no_dbos_row_names_the_session_once_the_worker_ran(
    admin_url: str, dbos: DBOSClient
) -> None:
    session = str(uuid.uuid4())  # fresh, so rows of earlier runs do not count
    jobs = DbosJobQueue(dbos, app_version="local")
    request = CheckRequest(channel="web", text="Czy we Włoszech był strajk generalny?")
    payload = CheckInput(
        request=request, session_id=session, received_at=datetime.now(UTC)
    )
    asyncio.run(jobs.enqueue(CHECK, payload))
    assert dbos_rows(admin_url, session) > 0
    eraser = build_app_repositories(DatabaseSettings()).eraser
    asyncio.run(delete_subject("session_id", session, eraser, jobs))
    if "MERITUM_TEST_WORKER" not in os.environ:
        pytest.skip(
            "DBOS rows go when the worker runs delete_subject (worker#24); "
            "start it and set MERITUM_TEST_WORKER=1"
        )
    deadline = time.monotonic() + WORKER_WAIT_SECONDS
    while dbos_rows(admin_url, session) and time.monotonic() < deadline:
        time.sleep(1)
    assert dbos_rows(admin_url, session) == 0
