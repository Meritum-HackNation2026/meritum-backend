"""Steps for POST and GET /api/v1/checks (checks.feature, security.feature).

The app runs with core's InMemoryJobQueue in place of DBOS, so no database.
"""

import logging
from http import HTTPStatus
from typing import override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks import AnalysisStatus, AnalysisStep, CheckResult
from meritum_core.jobs.constants import PROGRESS_KEY
from meritum_core.jobs.fakes import InMemoryJobQueue

from meritum_backend.checks.constants import SESSION_HEADER
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

SESSION = "session-0123456789"


class _Records(logging.Handler):
    """Keeps every log message emitted while a request runs."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.messages: list[str] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _prepare(context: Context, body: dict[str, str]) -> None:
    """Build the app on a fake queue and keep the request body.

    Args:
        context: the behave context; gets ``client``, ``jobs`` and ``body``.
        body: the JSON body of the POST.
    """
    context.jobs = InMemoryJobQueue()
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    context.client = TestClient(app)
    context.body = body


@given('tekst "{text}" z kanału "{channel}" i nagłówkiem X-Meritum-Session')
def text_from_channel(context: Context, text: str, channel: str) -> None:
    """A text sent from one channel with a browser session id.

    Args:
        context: the behave context.
        text: the text to check.
        channel: the channel name.

    Features:
        US-SPR-01, F-01
    """
    _prepare(context, {"channel": channel, "text": text})


@given("tekst o długości {length:d} znaków")
def text_of_length(context: Context, length: int) -> None:
    """A web text of the given length.

    Args:
        context: the behave context.
        length: how many characters.

    Features:
        US-SPR-01, F-01
    """
    _prepare(context, {"channel": "web", "text": "a" * length})


@given('wejście "{value}"')
def link_input(context: Context, value: str) -> None:
    """A link pasted into the web form.

    Args:
        context: the behave context.
        value: the link.

    Features:
        US-SPR-07, F-01
    """
    _prepare(context, {"channel": "web", "url": value})


@given('tekst "{text}"')
def web_text(context: Context, text: str) -> None:
    """A text sent from the web form.

    Args:
        context: the behave context.
        text: the text to check.

    Features:
        US-BEZ-04, F-20
    """
    _prepare(context, {"channel": "web", "text": text})


@when("klient wysyła POST /api/v1/checks")
def post_check(context: Context) -> None:
    """Send the check and record every log message emitted meanwhile.

    Args:
        context: the behave context; gets ``response`` and ``logs``.

    Features:
        US-SPR-01, F-01
    """
    records = _Records()
    root = logging.getLogger()
    level = root.level
    root.addHandler(records)
    root.setLevel(logging.DEBUG)
    try:
        context.response = context.client.post(
            "/api/v1/checks", json=context.body, headers={SESSION_HEADER: SESSION}
        )
    finally:
        root.removeHandler(records)
        root.setLevel(level)
    context.logs = records.messages


@then("odpowiedź ma kod 202 i identyfikator sprawdzenia")
def accepted(context: Context) -> None:
    """The check was accepted and has an id.

    Args:
        context: the behave context with ``response``.

    Features:
        US-SPR-01, F-01
    """
    assert context.response.status_code == HTTPStatus.ACCEPTED
    context.check_id = context.response.json()["check_id"]
    assert context.check_id


@then(
    "GET /api/v1/checks/{{id}} zwraca AnalysisStatus z krokami,"
    " a po zakończeniu pole result z CheckResult"
)
def status_then_result(context: Context) -> None:
    """Poll the check before and after the worker publishes its result.

    Args:
        context: the behave context with ``client``, ``jobs`` and ``check_id``.

    Features:
        US-SPR-01, US-BEZ-07, F-01, F-21
    """
    path = f"/api/v1/checks/{context.check_id}"
    running = AnalysisStatus.model_validate(context.client.get(path).json())
    assert running.steps
    assert running.result is None
    result = CheckResult(
        check_id=context.check_id,
        status="needs_clarification",
        message="Doprecyzuj pytanie.",
        corpus_version="test",
    )
    step = AnalysisStep(code="write_answer", status="done")
    final = AnalysisStatus(check_id=context.check_id, steps=[step], result=result)
    context.jobs.publish(context.check_id, PROGRESS_KEY, final)
    response = context.client.get(path)
    done = AnalysisStatus.model_validate(response.json())
    assert done.result is not None
    assert done.result.ai_disclosure is True
    assert response.headers["AI-Disclosure"] == "mode=ai-originated"


def _rejected_with(context: Context, key: str) -> None:
    assert context.response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert context.response.json() == {"message_key": key}
    assert context.jobs.enqueued == []


@then(
    "odpowiedź ma kod 422 z kluczem komunikatu po polsku i żaden workflow nie startuje"
)
def rejected_too_long(context: Context) -> None:
    """The text is too long: copy key errors.too_long, nothing enqueued.

    Args:
        context: the behave context with ``response`` and ``jobs``.

    Features:
        US-SPR-01, F-01
    """
    _rejected_with(context, "errors.too_long")


@then(
    "odpowiedź ma kod 422 z komunikatem, że przyjmujemy tylko adresy"
    " http:// albo https://"
)
def rejected_scheme(context: Context) -> None:
    """The link is not http(s): copy key errors.invalid_url, nothing enqueued.

    Args:
        context: the behave context with ``response`` and ``jobs``.

    Features:
        US-SPR-07, F-01
    """
    _rejected_with(context, "errors.invalid_url")


@then(
    'wejście workflowu w JobQueue nie zawiera "{phone}" ani "{pesel}",'
    " a logi też ich nie mają"
)
def masked_before_queue(context: Context, phone: str, pesel: str) -> None:
    """The enqueued input and the logs hold no raw personal data.

    Args:
        context: the behave context with ``jobs`` and ``logs``.
        phone: the phone number that must not leak.
        pesel: the PESEL number that must not leak.

    Features:
        US-BEZ-04, F-20
    """
    assert context.response.status_code == HTTPStatus.ACCEPTED
    [job] = context.jobs.enqueued
    sent = job.payload.model_dump_json()
    leaked = [
        s for s in (phone, pesel) if s in sent or any(s in m for m in context.logs)
    ]
    assert not leaked, leaked
