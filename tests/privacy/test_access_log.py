"""The access log never keeps a session id from the deletion path."""

import logging

import pytest

from meritum_backend.main import create_app
from meritum_backend.privacy.constants import ACCESS_LOGGER
from meritum_backend.settings import Settings

from .conftest import SESSION

DB = "postgresql://x:x@127.0.0.1:1/x"


def log_access(path: str) -> None:
    # the call uvicorn's HTTP protocol makes for every response
    logging.getLogger(ACCESS_LOGGER).info(
        '%s - "%s %s HTTP/%s" %d', "203.0.113.7:5123", "DELETE", path, "1.1", 202
    )


@pytest.mark.parametrize("query", ["", "?x=1"])
def test_session_id_in_the_deletion_path_is_masked(
    caplog: pytest.LogCaptureFixture, query: str
) -> None:
    create_app(Settings(database_url=DB))
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        log_access(f"/api/v1/sessions/{SESSION}/checks{query}")
    assert SESSION not in caplog.text
    assert f"/api/v1/sessions/{{session_id}}/checks{query}" in caplog.text


def test_other_paths_are_logged_as_sent(caplog: pytest.LogCaptureFixture) -> None:
    create_app(Settings(database_url=DB))
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        log_access("/api/v1/checks/wf-1")
    assert "/api/v1/checks/wf-1" in caplog.text


def test_building_the_app_twice_installs_one_filter() -> None:
    create_app(Settings(database_url=DB))
    create_app(Settings(database_url=DB))
    filters = logging.getLogger(ACCESS_LOGGER).filters
    assert len(filters) == 1
