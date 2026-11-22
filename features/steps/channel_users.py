"""Steps for checks from Discord, SMS and MCP (security.feature).

The app runs with core's InMemoryJobQueue in place of DBOS; the backend itself
writes nothing to a database, so the queue and the logs are what is checked.
"""

import logging
from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.jobs.contracts import CheckInput
from meritum_core.jobs.fakes import InMemoryJobQueue
from pydantic import SecretStr

from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

_DISCORD_USER = "1234567890"


def _prepare(context: Context, user: str, requests: int) -> None:
    context.jobs = InMemoryJobQueue()
    settings = Settings(
        database_url="postgresql://x:x@127.0.0.1:1/x",
        channel_hash_salt=SecretStr("behave-salt"),
    )
    app = create_app(settings)
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_settings] = lambda: settings
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides[get_check_gate] = lambda: gate
    context.use_ready_probe(app)
    context.client = TestClient(app)
    context.user = user
    context.requests = requests


@given('POST /api/v1/checks z channel "discord" i identyfikatorem użytkownika "{user}"')
def discord_check(context: Context, user: str) -> None:
    """One Discord check carrying the raw user id.

    Args:
        context: the behave context.
        user: the Discord user id.

    Features:
        US-BEZ-06, US-WTY-08, F-20
    """
    _prepare(context, user, 1)


@given("dwa żądania z tym samym identyfikatorem użytkownika Discorda")
def two_discord_checks(context: Context) -> None:
    """Two Discord checks from one user.

    Args:
        context: the behave context.

    Features:
        US-BEZ-06, US-WTY-08, F-20
    """
    _prepare(context, _DISCORD_USER, 2)


@when("API zleca workflow")
@when("API liczy skrót")
def post_discord_checks(context: Context) -> None:
    """Send the checks and keep every log message emitted meanwhile.

    Args:
        context: the behave context; gets ``inputs`` and ``logs``.

    Features:
        US-BEZ-06, US-WTY-08, F-20
    """
    body = {
        "channel": "discord",
        "text": "Czy to prawda?",
        "channel_user_id": context.user,
    }
    root = logging.getLogger()
    handler = logging.Handler(logging.DEBUG)
    messages: list[str] = []
    handler.emit = lambda record: messages.append(record.getMessage())
    level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        for _ in range(context.requests):
            response = context.client.post("/api/v1/checks", json=body)
            assert response.status_code == HTTPStatus.ACCEPTED, response.text
    finally:
        root.removeHandler(handler)
        root.setLevel(level)
    context.logs = messages
    context.inputs = [
        CheckInput.model_validate(j.payload) for j in context.jobs.enqueued
    ]


@then(
    'wejście workflowu ma channel_user_hash równy session_id, a "{user}" nie ma'
    " w kolejce, bazie ani logach"
)
def hashed_input(context: Context, user: str) -> None:
    """The workflow input carries only the hash; the raw id leaks nowhere.

    Args:
        context: the behave context with ``inputs`` and ``logs``.
        user: the raw Discord user id.

    Features:
        US-BEZ-06, US-WTY-08, F-20
    """
    [payload] = context.inputs
    assert payload.channel_user_hash is not None
    assert payload.channel_user_hash == payload.session_id
    assert user not in payload.model_dump_json()
    assert not [m for m in context.logs if user in m]


@then("oba mają ten sam channel_user_hash")
def same_hash(context: Context) -> None:
    """Both checks of one user carry the same hash.

    Args:
        context: the behave context with ``inputs``.

    Features:
        US-BEZ-06, US-WTY-08, F-20
    """
    first, second = context.inputs
    assert first.channel_user_hash is not None
    assert first.channel_user_hash == second.channel_user_hash
