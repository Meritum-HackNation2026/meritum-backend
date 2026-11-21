"""Steps of features/channels.feature: the result cache shared by every channel.

A fake worker finishes every job at once (no network in CI); the cache and the
check records live in memory.
"""

import asyncio
from pathlib import Path
from typing import override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks import CheckResult, Escalation
from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.jobs.contracts import (
    CheckOutput,
    EscalateClaimInput,
    EscalateClaimOutput,
)
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_records, get_result_cache
from meritum_backend.checks.constants import SESSION_HEADER, SUBSTANTIVE_FIELDS
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "check_result.json"
_RESULT = CheckResult.model_validate_json(_FIXTURE.read_text(encoding="utf-8"))
_FAILURE = CheckResult(
    check_id="x",
    status="technical_failure",
    message="Spróbuj ponownie.",
    failure_code="provider_unavailable",
    corpus_version=_RESULT.corpus_version,
)
_OWN_CASE = Escalation(state="updated", case_id="#S-9")
_TEXT = 'Czy "Wrocław" był jedynym miastem w Polsce?'


class _Worker(InMemoryJobQueue):
    """`check` ends with ``result`` and ``case``; `escalate_claim` with _OWN_CASE."""

    def __init__(self, result: CheckResult, case: Escalation | None) -> None:
        super().__init__()
        self._result, self._case = result, case

    def checks(self) -> int:
        return sum(job.spec.name == "check" for job in self.enqueued)

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        job = next((j for j in self.enqueued if j.workflow_id == workflow_id), None)
        if job is None:
            return None
        if job.spec.name == "check":
            update = {"check_id": workflow_id, "escalation": self._case}
            output = CheckOutput(result=self._result.model_copy(update=update))
        else:
            output = EscalateClaimOutput(escalation=_OWN_CASE)
        dump = output.model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=dump)


def _start(
    context: Context, result: CheckResult, case: Escalation | None = None
) -> None:
    context.jobs = _Worker(result, case)
    context.records = InMemoryCheckRecordRepository()
    cache = MemoryResultCache()
    settings = Settings(database_url="postgresql://x:x@127.0.0.1:1/x")
    app = create_app(settings)
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides |= {
        get_jobs: lambda: context.jobs,
        get_settings: lambda: settings,
        get_check_gate: lambda: gate,
        get_records: lambda: context.records,
        get_result_cache: lambda: cache,
    }
    context.use_ready_probe(app)
    context.client = TestClient(app)
    context.results = [_check(context, "web", context.checked, "session-aaaaaaaaaa")]


def _check(context: Context, channel: str, text: str, session: str) -> CheckResult:
    body = {"channel": channel, "text": text}
    headers = {SESSION_HEADER: session}
    posted = context.client.post("/api/v1/checks", json=body, headers=headers)
    assert posted.status_code == 202, posted.text  # ruff: ignore[magic-value-comparison]  # HTTP 202 Accepted
    polled = context.client.get(f"/api/v1/checks/{posted.json()['check_id']}")
    return CheckResult.model_validate(polled.json()["result"])


def _again(context: Context, text: str | None = None) -> None:
    sent = text or context.checked
    context.results.append(_check(context, "extension", sent, "session-bbbbbbbbbb"))


@given('sprawdzenie tekstu "{text}" z formularza zakończyło się 10 minut temu')
def checked_from_web(context: Context, text: str) -> None:
    """A web check of ``text`` finished and filled the cache (10 minutes < 2 h).

    Args:
        context: the behave context.
        text: the checked text.
    """
    context.checked = text
    _start(context, _RESULT)


@when("ten sam tekst z innymi spacjami i cudzysłowami przychodzi z wtyczki")
def same_text_from_extension(context: Context) -> None:
    """The extension sends the text with doubled spaces and a typographic dash.

    Args:
        context: the behave context.
    """
    # the scenario's text has no quotes; its hyphen stands in (core maps both)
    _again(context, f"  {context.checked.replace(' ', '  ')}  ".replace("-", "\u2013"))


@then(
    "część merytoryczna CheckResult jest identyczna jako JSON,"
    " z tym samym werdyktem i tą samą publikacją"
)
def same_substance(context: Context) -> None:
    """Both results have the same substantive JSON.

    Args:
        context: the behave context.
    """
    fields = set(SUBSTANTIVE_FIELDS)
    first, second = (r.model_dump_json(include=fields) for r in context.results)
    assert first == second


@then("workflow sprawdzania nie startuje drugi raz, a CheckRecord.cache_hit jest true")
def one_workflow(context: Context) -> None:
    """One `check` workflow ran; the hit's record says cache_hit.

    Args:
        context: the behave context.
    """
    assert context.jobs.checks() == 1
    hit = context.results[-1].check_id
    record = asyncio.run(context.records.get(hit))
    assert record is not None
    assert record.cache_hit


@given('sprawdzenie zakończyło się stanem "technical_failure"')
def failed_check(context: Context) -> None:
    """A check of the text ended with a technical failure.

    Args:
        context: the behave context.
    """
    context.checked = _TEXT
    _start(context, _FAILURE)


@when("to samo wejście przychodzi ponownie")
def same_input_again(context: Context) -> None:
    """The same text arrives again.

    Args:
        context: the behave context.
    """
    _again(context)


@then("startuje nowy workflow")
def new_workflow(context: Context) -> None:
    """A second `check` workflow ran.

    Args:
        context: the behave context.
    """
    assert context.jobs.checks() == 2  # ruff: ignore[magic-value-comparison]  # the first check and the retry


@given('wynik w pamięci pochodzi ze sprawdzenia, które utworzyło sprawę "{case_id}"')
def cached_with_case(context: Context, case_id: str) -> None:
    """The cached result came from a check that created ``case_id``.

    Args:
        context: the behave context.
        case_id: the other check's case.
    """
    context.checked = _TEXT
    _start(context, _RESULT, Escalation(state="created", case_id=case_id))


@when("inna sesja dostaje ten wynik z pamięci")
def other_session_hits(context: Context) -> None:
    """Another session sends the same text.

    Args:
        context: the behave context.
    """
    _again(context)


@then(
    "CheckResult.escalation jest policzone dla tej sesji"
    ' i nie zawiera cudzego stanu ani numeru "{case_id}"'
)
def own_escalation(context: Context, case_id: str) -> None:
    """The hit's escalation is its own escalate_claim outcome.

    Args:
        context: the behave context.
        case_id: the other check's case.
    """
    escalation = context.results[-1].escalation
    assert escalation == _OWN_CASE
    assert escalation.case_id != case_id


@then(
    "powtórzone pytanie bez odpowiedzi zwiększa licznik powtórzeń"
    " tak samo jak bez pamięci"
)
def repeat_counted(context: Context) -> None:
    """The unanswered claim goes to escalate_claim with the hit's own check id.

    Args:
        context: the behave context.
    """
    hit = context.results[-1].check_id
    sent = [j.payload for j in context.jobs.enqueued if j.spec.name == "escalate_claim"]
    assert sent == [EscalateClaimInput(check_id=hit, claim_index=0, reason="cache_hit")]
