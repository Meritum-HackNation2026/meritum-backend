"""Steps for the progress stream GET /api/v1/checks/{id}/events (checks.feature).

The app runs on core's InMemoryJobQueue: the scenario publishes the progress a
workflow would write, then reads the whole event stream, with no worker.
"""

import json
from datetime import UTC, date, datetime
from typing import override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks import AnalysisStatus, AnalysisStep, CheckResult
from meritum_core.checks.contracts import AiMarker, ClaimResult
from meritum_core.jobs.constants import PROGRESS_KEY
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

CHECK_ID = "wf-events-1"
RESULT = CheckResult(
    check_id=CHECK_ID,
    status="done",
    claims=[
        ClaimResult(
            claim="We Włoszech odbył się strajk generalny.",
            claim_date=date(2026, 11, 21),
            claim_date_source="today",
            verdict="insufficient_evidence",
            explanation="Źródła w korpusie nie opisują takiego strajku.",
            unresolved="Data i zasięg strajku.",
        )
    ],
    limitations=["Korpus obejmuje tylko źródła polskie."],
    limitation_codes=["corpus_scope"],
    corpus_version="test",
    ai_marker=AiMarker(
        provider="stub", model="stub", generated_at=datetime(2026, 11, 21, tzinfo=UTC)
    ),
)


class _Jobs(InMemoryJobQueue):
    """Reports the check as running, or as finished with RESULT."""

    def __init__(self, *, finished: bool) -> None:
        super().__init__()
        self.finished = finished

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        if not self.finished:
            return JobState(workflow_id=workflow_id, status="PENDING")
        output = CheckOutput(result=RESULT).model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


def _publish(context: Context, steps: dict[str, str], *, finished: bool) -> None:
    context.jobs = _Jobs(finished=finished)
    progress = AnalysisStatus(
        check_id=CHECK_ID,
        steps=[
            AnalysisStep.model_validate({"code": c, "status": s})
            for c, s in steps.items()
        ],
        result=RESULT,
    )
    context.jobs.publish(CHECK_ID, PROGRESS_KEY, progress)


@given("trwa sprawdzenie tekstu bez linku")
def text_check_running(context: Context) -> None:
    """A running text check: several research steps at once, no page to fetch.

    Args:
        context: the behave context; gets ``jobs``.

    Features:
        US-SPR-02, F-09
    """
    steps = {
        "receive": "done",
        "fetch_url": "skipped",
        "search_corpus": "active",
        "search_web": "active",
        "search_fact_checks": "active",
        "verify_citations": "pending",
    }
    _publish(context, steps, finished=False)


@given("cytaty nie przeszły jeszcze weryfikacji")
def citations_unverified(context: Context) -> None:
    """The worker has a draft answer while verify_citations still runs.

    Args:
        context: the behave context; gets ``jobs``.

    Features:
        US-SPR-02, F-09
    """
    steps = {"receive": "done", "verify_citations": "active", "write_answer": "active"}
    _publish(context, steps, finished=False)


@given('workflow kończy się stanem "done"')
def workflow_done(context: Context) -> None:
    """The workflow finished and its output holds the full CheckResult.

    Args:
        context: the behave context; gets ``jobs``.

    Features:
        US-SPR-02, F-09
    """
    _publish(context, {"receive": "done", "save_record": "done"}, finished=True)


@when("klient otwiera GET /api/v1/checks/{{id}}/events")
@when("serwer wysyła wersję wstępną odpowiedzi")
@when("serwer wysyła ostatnie zdarzenie")
def stream_read(context: Context) -> None:
    """Read the event stream of the check until the server closes it.

    Args:
        context: the behave context with ``jobs``; gets ``events``.

    Features:
        US-SPR-02, F-09
    """
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides[get_check_gate] = lambda: gate
    path = f"/api/v1/checks/{CHECK_ID}/events"
    with TestClient(app).stream("GET", path) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        data = [
            line.removeprefix("data: ")
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]
    context.events = [AnalysisStatus.model_validate(json.loads(d)) for d in data]


@then(
    "dostaje zdarzenia AnalysisStatus, w których kilka kroków badań"
    ' ma jednocześnie stan "active"'
)
def parallel_steps(context: Context) -> None:
    """Some event has two or more active steps.

    Args:
        context: the behave context with ``events``.

    Features:
        US-SPR-02, F-09
    """
    active = [sum(s.status == "active" for s in e.steps) for e in context.events]
    assert max(active) > 1


@then('krok "{code}" ma stan "{state}"')
def step_state(context: Context, code: str, state: str) -> None:
    """The step has the state in the latest event.

    Args:
        context: the behave context with ``events``.
        code: the step code.
        state: the expected state.

    Features:
        US-SPR-02, F-09
    """
    steps = {s.code: s.status for s in context.events[-1].steps}
    assert steps[code] == state


@then("zdarzenie nie zawiera werdyktu")
def no_verdict(context: Context) -> None:
    """No event carries a result, so no verdict.

    Args:
        context: the behave context with ``events``.

    Features:
        US-SPR-02, F-09
    """
    assert context.events
    assert all(e.result is None for e in context.events)


@then(
    "zdarzenie zawiera AnalysisStatus z pełnym CheckResult w polu result,"
    " a strumień się zamyka"
)
def full_result_last(context: Context) -> None:
    """The last event, read after the server closed the stream, has the result.

    Args:
        context: the behave context with ``events``.

    Features:
        US-SPR-02, F-09
    """
    assert context.events[-1].result == RESULT
