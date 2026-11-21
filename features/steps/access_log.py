"""Steps for the access log scenario (security.feature): no session id in it."""

import logging
from typing import override

from behave import given, then, when
from behave.runner import Context

from meritum_backend.main import create_app
from meritum_backend.privacy.constants import ACCESS_LOGGER
from meritum_backend.settings import Settings

SESSION = "0b6f3c1e-5d2a-4f7b-9c8e-1a2b3c4d5e6f"


class _Lines(logging.Handler):
    """Keeps every formatted access log line."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@given("żądanie DELETE /api/v1/sessions/<session_id>/checks")
def deletion_request(context: Context) -> None:
    """The app is built, so its access log filter is installed.

    Args:
        context: the behave context; gets ``path``, ``lines`` and ``level``.

    Features:
        US-BEZ-05, F-20
    """
    create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    context.path = f"/api/v1/sessions/{SESSION}/checks"
    context.lines = _Lines()
    access = logging.getLogger(ACCESS_LOGGER)
    context.level = access.level
    access.setLevel(logging.INFO)
    access.addHandler(context.lines)


@when("serwer zapisuje log dostępu")
def server_logs_access(context: Context) -> None:
    """Log the line uvicorn writes after the response.

    Args:
        context: the behave context with ``path``.

    Features:
        US-BEZ-05, F-20
    """
    logging.getLogger(ACCESS_LOGGER).info(
        '%s - "%s %s HTTP/%s" %d',
        "203.0.113.7:5123",
        "DELETE",
        context.path,
        "1.1",
        202,
    )


@then("w logu ścieżka ma zamaskowany identyfikator sesji")
def log_has_no_session(context: Context) -> None:
    """The line names the path pattern, not the session.

    Args:
        context: the behave context with ``lines`` and ``level``.

    Features:
        US-BEZ-05, F-20
    """
    access = logging.getLogger(ACCESS_LOGGER)
    access.removeHandler(context.lines)
    access.setLevel(context.level)
    [line] = context.lines.lines
    assert SESSION not in line
    assert "/api/v1/sessions/{session_id}/checks" in line
