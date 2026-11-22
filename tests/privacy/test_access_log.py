"""The access log never keeps a session id from the deletion path."""

import logging

import pytest

from meritum_backend.main import create_app
from meritum_backend.privacy.access_log import SessionIdFilter
from meritum_backend.privacy.constants import ACCESS_LOGGER
from meritum_backend.settings import Settings

from .conftest import SESSION

DB = "postgresql://x:x@127.0.0.1:1/x"


def log_access(path: str) -> None:
    # the call uvicorn's HTTP protocol makes for every response
    logging.getLogger(ACCESS_LOGGER).info(
        '%s - "%s %s HTTP/%s" %d', "203.0.113.7:5123", "DELETE", path, "1.1", 202
    )


@pytest.mark.parametrize(
    ("prefix", "suffix"), [("", ""), ("", "?x=1"), ("/meritum", "/")]
)
def test_session_id_in_the_deletion_path_is_masked(
    caplog: pytest.LogCaptureFixture, prefix: str, suffix: str
) -> None:
    create_app(Settings(database_url=DB))
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        log_access(f"{prefix}/api/v1/sessions/{SESSION}/checks{suffix}")
    assert SESSION not in caplog.text
    assert f"{prefix}/api/v1/sessions/{{session_id}}/checks{suffix}" in caplog.text


def test_other_paths_are_logged_as_sent(caplog: pytest.LogCaptureFixture) -> None:
    create_app(Settings(database_url=DB))
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        log_access("/api/v1/checks/wf-1")
    assert "/api/v1/checks/wf-1" in caplog.text


def test_building_the_app_twice_installs_one_filter() -> None:
    create_app(Settings(database_url=DB))
    create_app(Settings(database_url=DB))
    filters = logging.getLogger(ACCESS_LOGGER).filters
    assert sum(isinstance(f, SessionIdFilter) for f in filters) == 1


@pytest.mark.parametrize("query", ["?session={s}", "?a=1&session={s}&b=2"])
def test_session_id_in_the_notification_stream_query_is_masked(
    caplog: pytest.LogCaptureFixture, query: str
) -> None:
    create_app(Settings(database_url=DB))
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        log_access("/api/v1/notifications/stream" + query.format(s=SESSION))
    assert SESSION not in caplog.text
    assert "session={session_id}" in caplog.text


def test_demo_token_in_the_link_path_is_masked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    create_app(Settings(database_url=DB))
    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        log_access("/api/v1/auth/demo/SECRETTOKEN123")
    assert "SECRETTOKEN123" not in caplog.text
    assert "/api/v1/auth/demo/{token}" in caplog.text
