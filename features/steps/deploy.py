"""Steps for features/deploy.feature: readiness of the API and the worker.

The app runs on core's InMemoryJobQueue; the database check is a stub.
"""

import asyncio
import logging
from datetime import UTC, datetime
from http import HTTPStatus
from typing import override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.jobs.constants import READINESS_KEY
from meritum_core.jobs.contracts import ReadinessReport
from meritum_core.jobs.fakes import InMemoryJobQueue

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.health.api import get_readiness
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings


class _Records(logging.Handler):
    """Keeps every log message."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.messages: list[str] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _prepare(context: Context, report: ReadinessReport | None) -> None:
    context.jobs = InMemoryJobQueue()
    if report is not None:
        context.readiness_jobs.set_event(
            context.probe.workflow_id, READINESS_KEY, report
        )
    app = create_app(Settings())
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_readiness] = lambda: context.probe
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides[get_check_gate] = lambda: gate
    context.client = TestClient(app)


def _report(missing: list[str]) -> ReadinessReport:
    return ReadinessReport(
        missing_env=missing, unavailable_providers=[], checked_at=datetime.now(UTC)
    )


@given('raport gotowości workera wymienia brakującą zmienną "{name}"')
def worker_lacks(context: Context, name: str) -> None:
    """The worker reported one missing variable.

    Args:
        context: the behave context.
        name: the variable name.

    Features:
        US-WDR-08, F-30
    """
    _prepare(context, _report([name]))


@given("usługa jest niegotowa")
def not_ready(context: Context) -> None:
    """The worker reported a missing key.

    Args:
        context: the behave context.

    Features:
        US-BEZ-03, F-30
    """
    _prepare(context, _report(["MERITUM_LLM_API_KEY"]))


@given('worker zgłasza dostawcę "{name}" jako niedostępnego')
def worker_provider_down(context: Context, name: str) -> None:
    """The worker reported one unreachable provider and no missing variable.

    Args:
        context: the behave context.
        name: the provider name.

    Features:
        US-WDR-08, F-30
    """
    report = _report([]).model_copy(update={"unavailable_providers": [name]})
    _prepare(context, report)


@then("sprawdzenie zostaje przyjęte")
def check_accepted(context: Context) -> None:
    """The API enqueued the check instead of answering not_ready.

    Args:
        context: the behave context.

    Features:
        US-BEZ-03, F-30
    """
    assert context.response.status_code == HTTPStatus.ACCEPTED, context.response.text


@given("worker nie opublikował raportu od startu API")
def worker_silent(context: Context) -> None:
    """No readiness event was set.

    Args:
        context: the behave context.

    Features:
        US-WDR-08, F-30
    """
    _prepare(context, None)


@when("administrator otwiera GET /api/v1/health")
def open_health(context: Context) -> None:
    """Ask for readiness.

    Args:
        context: the behave context; gets ``response``.

    Features:
        US-WDR-08, F-30
    """
    context.response = context.client.get("/api/v1/health")


@when("obywatel wysyła sprawdzenie")
def send_check(context: Context) -> None:
    """Send a web check.

    Args:
        context: the behave context; gets ``response``.

    Features:
        US-BEZ-03, F-30
    """
    context.response = context.client.post(
        "/api/v1/checks",
        json={"channel": "web", "text": "Czy jutro jest strajk generalny?"},
        headers={SESSION_HEADER: "session-0123456789"},
    )


@then('odpowiedź ma kod 503 i wymienia nazwę "{name}"')
def lists_missing(context: Context, name: str) -> None:
    """503 naming the variable.

    Args:
        context: the behave context.
        name: the expected variable name.

    Features:
        US-WDR-08, F-30
    """
    assert context.response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert name in context.response.json()["missing_env"]


@then("log startu API zawiera tę samą listę")
def startup_log_lists(context: Context) -> None:
    """The startup log names the same missing variables as /api/v1/health.

    Args:
        context: the behave context.

    Features:
        US-WDR-08, F-30
    """
    records = _Records()
    logger = logging.getLogger("meritum_backend")
    logger.addHandler(records)
    try:
        asyncio.run(context.probe.log_startup())
    finally:
        logger.removeHandler(records)
    body = context.response.json()
    missing = ", ".join(body["missing_env"]) or "none"
    unavailable = ", ".join(body["unavailable_providers"]) or "none"
    expected = f"missing env {missing}, unavailable {unavailable}"
    assert any(message.endswith(expected) for message in records.messages)


@then('dostaje stan "{state}" z kodem "{code}", bez nazw kluczy w komunikacie')
def refused_not_ready(context: Context, state: str, code: str) -> None:
    """503 technical_failure / not_ready, naming no variable.

    Args:
        context: the behave context.
        state: the expected status.
        code: the expected failure code.

    Features:
        US-BEZ-03, F-30
    """
    body = context.response.json()
    assert context.response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert (body["status"], body["code"]) == (state, code)
    assert "MERITUM_LLM_API_KEY" not in context.response.text
    assert all(job.spec.name != "check" for job in context.jobs.enqueued)


@then("odpowiedź ma kod 503 z informacją, że worker nie zgłosił gotowości")
def worker_not_reported(context: Context) -> None:
    """503 saying the worker did not report.

    Args:
        context: the behave context.

    Features:
        US-WDR-08, F-30
    """
    assert context.response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert context.response.json()["worker"] == "not_reported"
