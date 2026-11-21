"""Deletion on real PostgreSQL: no app table keeps the session (local only).

Run with ``uv run pytest -m integration tests/privacy``. Needs
``MERITUM_TEST_DATABASE_URL`` (a PostgreSQL the user may create schemas in) and
the DBOS system tables in ``worker_local`` of the same database: start the worker
once, or run ``uv run dbos migrate -s "$URL" --schema worker_local``. The DBOS
rows themselves are deleted by the worker's ``delete_subject`` workflow and
checked in meritum-worker (worker/024).
"""

import asyncio
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from dbos import DBOSClient
from meritum_core.jobs.adapters import DbosJobQueue
from meritum_core.jobs.contracts import APPLICATION_NAME
from meritum_core.observability import build_app_repositories
from meritum_core.shared.database import DatabaseProvider, DatabaseSettings
from meritum_core.shared.database.adapters import apply_migrations
from psycopg import sql
from psycopg.conninfo import make_conninfo

from meritum_backend.privacy.api import delete_subject

from .conftest import ALL, SESSION, Remaining, Seed

APP_TABLES = ("check_records", "moderator_cases", "notifications")


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


def rows_naming(url: str, value: str) -> int:
    with psycopg.connect(url) as conn:
        return sum(
            conn.execute(
                sql.SQL("SELECT count(*) FROM {} t WHERE t::text LIKE %s").format(
                    sql.Identifier(table)
                ),
                (f"%{value}%",),
            ).fetchone()[0]  # ty: ignore[not-subscriptable]  # count(*) returns one row
            for table in APP_TABLES
        )


@pytest.mark.integration
def test_nothing_names_the_session_after_deletion(
    admin_url: str, app_url: str, seed: Seed, remaining: Remaining
) -> None:
    settings = DatabaseSettings(provider=DatabaseProvider.POSTGRES, url=app_url)
    repos = build_app_repositories(settings)
    seed(repos)
    assert rows_naming(app_url, SESSION) > 0
    client = DBOSClient(
        system_database_url=admin_url,
        dbos_system_schema="worker_local",
        application_name=APPLICATION_NAME,
    )
    try:
        before = len(client.list_workflows(name="delete_subject"))
        jobs = DbosJobQueue(client, app_version="local")
        asyncio.run(delete_subject("session_id", SESSION, repos.eraser, jobs))
        after = len(client.list_workflows(name="delete_subject"))
    finally:
        client.destroy()
    assert rows_naming(app_url, SESSION) == 0
    assert remaining(repos) == ALL - {"c_s"}
    assert after == before + 1
