"""Local PostgreSQL scenario for persistence of staff roles."""

import os
from collections.abc import Callable
from multiprocessing import get_context
from uuid import uuid4

import psycopg
import pytest
from behave import given, then, when
from behave.runner import Context
from features.constants import STAFF_TEST_PROCESS_TIMEOUT
from features.staff_backend import grant_role, verify_role
from meritum_core.shared.database.adapters import apply_migrations
from psycopg import sql
from psycopg.conninfo import make_conninfo


@given("backend z MERITUM_DATABASE_PROVIDER=postgres")
def postgres_staff_backend(context: Context) -> None:
    """Set up a fresh PostgreSQL schema for the backend processes.

    Args:
        context: the behave context; owns the test schema and environment.

    Features:
        US-MOD-05, F-25
    """
    url = os.environ["MERITUM_TEST_DATABASE_URL"]
    schema = f"staff_test_{uuid4().hex}"
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    context.add_cleanup(_drop_schema, url, schema)
    app_url = make_conninfo(url, options=f"-c search_path={schema}")
    apply_migrations(app_url)

    env = pytest.MonkeyPatch()
    context.add_cleanup(env.undo)
    env.setenv("MERITUM_DATABASE_PROVIDER", "postgres")
    env.setenv("MERITUM_DATABASE_URL", app_url)


def _drop_schema(url: str, schema: str) -> None:
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
        )


def _run_backend(target: Callable[[], None]) -> None:
    process = get_context("spawn").Process(target=target)
    process.start()
    process.join(timeout=STAFF_TEST_PROCESS_TIMEOUT)
    if process.is_alive():
        process.terminate()
        process.join()
    exit_code = process.exitcode
    process.close()
    assert exit_code == 0, f"backend process exited with {exit_code}"


@when("administrator nadaje rolę i backend się restartuje")
def grant_and_restart(context: Context) -> None:
    """Grant the role in a backend process that shuts down after the request.

    Args:
        context: the behave context managing the PostgreSQL test schema.

    Features:
        US-MOD-05, F-25
    """
    del context
    _run_backend(grant_role)


@then("konto personelu ma nadal tę rolę")
def role_survives_restart(context: Context) -> None:
    """Verify the granted role in a new backend process.

    Args:
        context: the behave context managing the PostgreSQL test schema.

    Features:
        US-MOD-05, F-25
    """
    del context
    _run_backend(verify_role)
