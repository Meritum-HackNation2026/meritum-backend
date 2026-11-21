"""Steps for the escalation scenarios of features/moderation.feature.

A fake worker stands in for meritum-worker: the check ``chk-1`` is finished and
every ``escalate_claim`` job ends with the next prepared case (no network in CI).
"""

from http import HTTPStatus
from pathlib import Path
from typing import Any, override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks import CheckResult, Escalation
from meritum_core.jobs.contracts import CheckOutput, EscalateClaimInput, WorkflowSpec
from meritum_core.jobs.contracts import EscalateClaimOutput as Saved
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from pydantic import BaseModel

from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "check_result.json"
RESULT = CheckResult.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
CLAIMS = "/api/v1/checks/chk-1/claims"
PHONE = "Dzwoniłem na 600 700 800 i nikt nie potwierdził."


class FakeWorker(InMemoryJobQueue):
    """Finished check ``chk-1``; escalations end with ``cases``, one per job."""

    def __init__(self, *cases: Escalation) -> None:
        super().__init__()
        self._cases = list(cases)
        self._saved: dict[str, Escalation] = {}

    @override
    async def enqueue[In: BaseModel](
        self,
        spec: WorkflowSpec[In, Any],
        payload: In,
        *,
        workflow_id: str | None = None,
    ) -> str:
        workflow_id = await super().enqueue(spec, payload, workflow_id=workflow_id)
        self._saved[workflow_id] = self._cases.pop(0)
        return workflow_id

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        if workflow_id == RESULT.check_id:
            output = CheckOutput(result=RESULT)
        elif workflow_id in self._saved:
            output = Saved(escalation=self._saved[workflow_id])
        else:
            return None
        dump = output.model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=dump)


def _client(context: Context, *cases: Escalation) -> None:
    """Build the app on a fake worker that saves ``cases`` in order.

    Args:
        context: the behave context; gets ``client`` and ``worker``.
        cases: what each escalate_claim job ends with.
    """
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    context.worker = FakeWorker(*cases)
    app.dependency_overrides[get_jobs] = lambda: context.worker
    context.client = TestClient(app)


def _claim(verdict: str) -> int:
    """Find the fixture's claim with ``verdict``.

    Args:
        verdict: the verdict code.

    Returns:
        The claim's index in the result.
    """
    return next(i for i, c in enumerate(RESULT.claims) if c.verdict == verdict)


@given(
    'wynik ma twierdzenie z werdyktem "brak wystarczających dowodów"'
    ' i Escalation ze stanem "recommended" bez numeru'
)
def recommended_claim(context: Context) -> None:
    """A result with an unanswered claim; the worker creates, then joins #S-12.

    Args:
        context: the behave context; gets ``client``, ``worker`` and ``claim``.

    Features:
        US-MOD-03, F-24
    """
    assert RESULT.escalation == Escalation(state="recommended")
    created = Escalation(state="created", case_id="#S-12")
    _client(context, created, Escalation(state="updated", case_id="#S-12"))
    context.claim = _claim("insufficient_evidence")


@when("obywatel wysyła POST /api/v1/checks/{{id}}/claims/{{n}}/escalate")
@when("obywatel przekazuje swoje twierdzenie")
def sends_escalate(context: Context) -> None:
    """Press „Przekaż moderatorom”.

    Args:
        context: the behave context with ``client`` and ``claim``; gets ``response``.

    Features:
        US-MOD-03, F-24
    """
    context.response = context.client.post(f"{CLAIMS}/{context.claim}/escalate")


@then(
    'odpowiedź ma Escalation ze stanem "created" i numerem "#S-12" albo, przy'
    ' dołączeniu do podobnej sprawy, ze stanem "updated" i jej numerem'
)
def case_number_given(context: Context) -> None:
    """Check the created case, then press again and join it.

    Args:
        context: the behave context with ``client``, ``claim`` and ``response``.

    Features:
        US-MOD-03, F-24
    """
    assert context.response.json() == {
        "escalation": {"state": "created", "case_id": "#S-12"},
        "message_key": "escalation.created",
    }
    again = context.client.post(f"{CLAIMS}/{context.claim}/escalate").json()
    assert again["escalation"] == {"state": "updated", "case_id": "#S-12"}


@given('wynik z werdyktem "fałszywe"')
def false_claim(context: Context) -> None:
    """A result with a false claim; the worker creates #S-13.

    Args:
        context: the behave context; gets ``client``, ``worker`` and ``claim``.

    Features:
        US-MOD-06, F-24
    """
    _client(context, Escalation(state="created", case_id="#S-13"))
    context.claim = _claim("false")
    context.before = context.client.get(f"/api/v1/checks/{RESULT.check_id}").json()


@when(
    "obywatel wysyła POST /api/v1/checks/{{id}}/claims/{{n}}/dispute"
    " z uzasadnieniem zawierającym numer telefonu"
)
def sends_dispute(context: Context) -> None:
    """Press „Zgłoś błąd” with a phone number in the reason.

    Args:
        context: the behave context with ``client`` and ``claim``; gets ``response``.

    Features:
        US-MOD-06, F-24
    """
    body = {"justification": PHONE}
    context.response = context.client.post(
        f"{CLAIMS}/{context.claim}/dispute", json=body
    )


@then(
    'sprawa ma powód "user_dispute", uzasadnienie jest zamaskowane,'
    " a obywatel dostaje numer sprawy"
)
def dispute_saved_masked(context: Context) -> None:
    """Check the enqueued job and the case number.

    Args:
        context: the behave context with ``worker``, ``claim`` and ``response``.

    Features:
        US-MOD-06, F-24
    """
    [job] = context.worker.enqueued
    assert job.payload == EscalateClaimInput(
        check_id=RESULT.check_id,
        claim_index=context.claim,
        reason="user_dispute",
        justification_masked="Dzwoniłem na [telefon] i nikt nie potwierdził.",
    )
    assert context.response.json() == {
        "escalation": {"state": "created", "case_id": "#S-13"},
        "message_key": "result.report_error_done",
    }


@then("wynik dla innych pytających się nie zmienia")
def result_unchanged(context: Context) -> None:
    """Read the check again: the result is the one read before the dispute.

    Args:
        context: the behave context with ``client`` and ``before``.

    Features:
        US-MOD-06, F-24
    """
    body = context.client.get(f"/api/v1/checks/{RESULT.check_id}").json()
    assert body == context.before


@given("podobne twierdzenie jest już w otwartej sprawie od innej sesji")
def similar_case_open(context: Context) -> None:
    """The worker joins any escalation to the open case #S-7.

    Args:
        context: the behave context; gets ``client``, ``worker`` and ``claim``.

    Features:
        US-MOD-03, F-24
    """
    _client(context, Escalation(state="updated", case_id="#S-7"))
    context.claim = _claim("insufficient_evidence")


@then("komunikat nie mówi, że ktoś inny pytał o to samo")
def no_other_askers(context: Context) -> None:
    """The answer holds only the case and the join message, nothing about askers.

    Args:
        context: the behave context with ``response``.

    Features:
        US-MOD-03, F-24
    """
    assert context.response.status_code == HTTPStatus.OK
    assert context.response.json() == {
        "escalation": {"state": "updated", "case_id": "#S-7"},
        "message_key": "escalation.updated",
    }
