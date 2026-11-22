"""Steps for the limit scenarios of features/security.feature.

Apps run on core's InMemoryJobQueue and an in-memory rate counter; two apps on one
counter stand for two API instances on the shared PostgreSQL table.
"""

from http import HTTPStatus

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.jobs.fakes import InMemoryJobQueue

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import (
    CheckGate,
    LimitSettings,
    get_check_gate,
)
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

_BODY = {"channel": "web", "text": "Czy szczepionki powodują autyzm?"}
_HEADERS = {SESSION_HEADER: "session-0123456789"}


def _client(context: Context, gate: CheckGate) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_check_gate] = lambda: gate
    context.use_ready_probe(app)
    return TestClient(app)


def _instances(context: Context, count: int, pending: int = 0) -> None:
    context.jobs = InMemoryJobQueue()
    counter = MemoryRateCounter()
    gates = [
        CheckGate(counter, FixedPendingChecks(pending), context.limits)
        for _ in range(count)
    ]
    context.clients = [_client(context, gate) for gate in gates]


def _post(client: TestClient) -> int:
    return client.post("/api/v1/checks", json=_BODY, headers=_HEADERS).status_code


@given("limit {limit:d} sprawdzeń na minutę dla jednego adresu IP")
def ip_limit(context: Context, limit: int) -> None:
    """One API instance with the given per-address limit.

    Args:
        context: the behave context; gets ``limits``, ``jobs`` and ``clients``.
        limit: checks per address per minute.

    Features:
        US-BEZ-02, F-20
    """
    context.limits = LimitSettings(checks_per_ip_per_minute=limit)
    _instances(context, 1)


@when("z tego adresu przychodzi {nth:d}. sprawdzenie w tej samej minucie")
def nth_check(context: Context, nth: int) -> None:
    """Send ``nth`` checks from one address; keep the last answer.

    Args:
        context: the behave context with ``clients``; gets ``response``.
        nth: how many checks to send.

    Features:
        US-BEZ-02, F-20
    """
    [client] = context.clients
    for _ in range(nth - 1):
        assert _post(client) == HTTPStatus.ACCEPTED
    context.response = client.post("/api/v1/checks", json=_BODY, headers=_HEADERS)


@then("odpowiedź ma kod 429, nagłówek Retry-After i komunikat po polsku")
def limited(context: Context) -> None:
    """429 with Retry-After and the copy key of the Polish message.

    Args:
        context: the behave context with ``response``.

    Features:
        US-BEZ-02, F-20
    """
    assert context.response.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert int(context.response.headers["Retry-After"]) > 0
    assert context.response.json()["message_key"] == "errors.rate_limited"


@then("odpowiedź nie zawiera werdyktu")
def no_verdict(context: Context) -> None:
    """The answer holds only the message key, no result or verdict.

    Args:
        context: the behave context with ``response``.

    Features:
        US-BEZ-02, F-20
    """
    assert context.response.json().keys() == {"message_key"}


@given("dwie instancje API korzystające z jednego wspólnego licznika")
def two_instances(context: Context) -> None:
    """Two apps on one rate counter (the shared table in production).

    Args:
        context: the behave context; gets ``limits``, ``jobs`` and ``clients``.

    Features:
        US-BEZ-02, F-20, ADR-18
    """
    context.limits = LimitSettings()
    _instances(context, 2)


@when(
    "{first:d} zapytań trafia do pierwszej i {second:d} do drugiej"
    " przy limicie {limit:d}"
)
def split_traffic(context: Context, first: int, second: int, limit: int) -> None:
    """Send checks from one address to both instances; keep every status.

    Args:
        context: the behave context with ``clients``; gets ``statuses``.
        first: checks sent to the first instance.
        second: checks sent to the second instance.
        limit: the per-address limit the instances share.

    Features:
        US-BEZ-02, F-20, ADR-18
    """
    assert context.limits.checks_per_ip_per_minute == limit
    one, two = context.clients
    context.statuses = [_post(one) for _ in range(first)]
    context.statuses += [_post(two) for _ in range(second)]


@then("{nth:d}. zapytanie dostaje 429")
def nth_limited(context: Context, nth: int) -> None:
    """Only the ``nth`` check is refused.

    Args:
        context: the behave context with ``statuses``.
        nth: the position of the refused check.

    Features:
        US-BEZ-02, F-20, ADR-18
    """
    expected = [HTTPStatus.ACCEPTED] * (nth - 1) + [HTTPStatus.TOO_MANY_REQUESTS]
    assert context.statuses == expected


@given("liczba oczekujących sprawdzeń osiągnęła próg z konfiguracji")
def queue_full(context: Context) -> None:
    """The worker's queue holds as many checks as the configured threshold.

    Args:
        context: the behave context; gets ``limits``, ``jobs`` and ``clients``.

    Features:
        US-WDR-03, F-23
    """
    context.limits = LimitSettings()
    _instances(context, 1, pending=context.limits.max_pending_checks)


@when("przychodzi nowe sprawdzenie")
def new_check(context: Context) -> None:
    """Send one check.

    Args:
        context: the behave context with ``clients``; gets ``response``.

    Features:
        US-WDR-03, F-23
    """
    [client] = context.clients
    context.response = client.post("/api/v1/checks", json=_BODY, headers=_HEADERS)


@then("odpowiedź ma kod 429 z komunikatem, a workflow nie jest zlecany")
def busy(context: Context) -> None:
    """429 with the busy copy key, nothing enqueued.

    Args:
        context: the behave context with ``response`` and ``jobs``.

    Features:
        US-WDR-03, F-23
    """
    assert context.response.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert context.response.json() == {"message_key": "errors.busy"}
    assert context.jobs.enqueued == []
