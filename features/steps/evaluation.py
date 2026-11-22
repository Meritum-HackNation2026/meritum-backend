"""Steps for features/observability.feature: the evaluation API over a fake worker."""

from datetime import UTC, datetime
from http import HTTPStatus
from typing import override

from behave import given, then, when
from behave.runner import Context
from features.constants import STAFF_ADMIN
from features.staff_support import csrf, signed_in
from meritum_core.checks.contracts import EvalCaseResult, EvalMetrics, EvalRun
from meritum_core.jobs.contracts import EVAL_RUN, EvalRunOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from meritum_core.shared.blobs.adapters import MemoryBlobStore

from meritum_backend.evaluation.api import get_blobs
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

NOW = datetime(2026, 11, 22, tzinfo=UTC)
CASES = 30
HEADER = "case_id,scenario,text,expected\n"


class FinishedWorker(InMemoryJobQueue):
    """Reports the runs put in ``done`` as finished, the rest as enqueued."""

    def __init__(self) -> None:
        super().__init__()
        self.done: dict[str, EvalRun] = {}

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        run = self.done.get(workflow_id)
        if run is None:
            return await super().state(workflow_id)
        output = EvalRunOutput(run=run).model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


def _run(run_id: str, f1: float, predicted: str) -> EvalRun:
    metrics = EvalMetrics(
        cases=1,
        macro_f1=f1,
        citation_coverage=None,
        citation_correctness=None,
        abstention=None,
        robustness=None,
        median_seconds=1,
        p95_seconds=1,
        max_seconds=1,
        input_tokens_per_check=1,
        output_tokens_per_check=1,
        cost_per_check_usd=0,
        cost_100_checks_usd=0,
        channel_consistency=None,
        information_loop=None,
    )
    case = EvalCaseResult(
        case_id="c1",
        scenario="A",
        expected="false",
        predicted=predicted,  # ty: ignore[invalid-argument-type]
        outcome="correct" if predicted == "false" else "wrong_decisive",
        received_at=NOW,
        answered_at=NOW,
    )
    return EvalRun(
        id=run_id,
        case_set="golden",
        status="done",
        corpus_version="v1",
        started_at=NOW,
        finished_at=NOW,
        metrics=metrics,
        cases=(case,),
    )


@given("zalogowany analityk")
def analyst(context: Context) -> None:
    """Build the app over a fake worker and sign in an analyst.

    Args:
        context: the behave context.

    Features:
        US-OBS-06, F-28
    """
    app = create_app(Settings(admin_emails=STAFF_ADMIN))
    context.worker = FinishedWorker()
    app.dependency_overrides[get_jobs] = lambda: context.worker
    blobs = MemoryBlobStore()
    app.dependency_overrides[get_blobs] = lambda: blobs
    admin = signed_in(app, STAFF_ADMIN)
    body = {"email": "analyst@example.com", "role": "analyst"}
    admin.post("/api/v1/staff", json=body, headers=csrf(admin))
    context.client = signed_in(app, "analyst@example.com")


@when('wysyła POST /api/v1/eval/runs z zestawem "golden"')
def start_golden(context: Context) -> None:
    """Start a golden-set run.

    Args:
        context: the behave context.

    Features:
        US-OBS-06, F-28
    """
    client = context.client
    context.response = client.post(
        "/api/v1/eval/runs", json={"dataset": "golden"}, headers=csrf(client)
    )


@then(
    "odpowiedź ma kod 202 z identyfikatorem przebiegu, a przebieg startuje w workerze"
)
def accepted(context: Context) -> None:
    """The run id is the id of an ``eval_run`` job.

    Args:
        context: the behave context.

    Features:
        US-OBS-06, F-28
    """
    assert context.response.status_code == HTTPStatus.ACCEPTED
    job = context.worker.enqueued[0]
    assert job.spec == EVAL_RUN
    assert job.workflow_id == context.response.json()["id"]


@given("plik CSV z 30 przypadkami w formacie przypadków")
def csv_file(context: Context) -> None:
    """Prepare a valid case file.

    Args:
        context: the behave context.

    Features:
        US-OBS-05, F-26
    """
    rows = "".join(f"c{i},A,Tekst {i},false\n" for i in range(CASES))
    context.file = (HEADER + rows).encode()


@when("analityk wysyła go na POST /api/v1/eval/datasets")
def upload(context: Context) -> None:
    """Upload the file.

    Args:
        context: the behave context.

    Features:
        US-OBS-05, F-26
    """
    client = context.client
    context.response = client.post(
        "/api/v1/eval/datasets",
        files={"file": ("cases.csv", context.file)},
        headers=csrf(client),
    )


@then("zestaw jest zapisany i można na nim uruchomić przebieg")
def dataset_runs(context: Context) -> None:
    """A run on the stored set is accepted as a user file run.

    Args:
        context: the behave context.

    Features:
        US-OBS-05, F-26
    """
    assert context.response.status_code == HTTPStatus.CREATED
    assert context.response.json()["cases"] == CASES
    client = context.client
    run = client.post(
        "/api/v1/eval/runs",
        json={"dataset": context.response.json()["id"]},
        headers=csrf(client),
    )
    assert run.status_code == HTTPStatus.ACCEPTED
    assert context.worker.enqueued[0].payload.case_set == "user_file"


@given("dwa zakończone przebiegi")
def two_runs(context: Context) -> None:
    """Start two runs and let the worker finish them with different results.

    Args:
        context: the behave context.

    Features:
        US-OBS-06, F-28
    """
    client = context.client
    context.ids = [
        client.post(
            "/api/v1/eval/runs", json={"dataset": "golden"}, headers=csrf(client)
        ).json()["id"]
        for _ in range(2)
    ]
    for run_id, f1, label in zip(
        context.ids, (0.5, 0.9), ("confirmed", "false"), strict=True
    ):
        context.worker.done[run_id] = _run(run_id, f1, label)


@when(
    "analityk otwiera GET /api/v1/eval/runs/compare z identyfikatorami obu przebiegów"
)
def compare(context: Context) -> None:
    """Open the comparison of the two runs.

    Args:
        context: the behave context.

    Features:
        US-OBS-06, F-28
    """
    a, b = context.ids
    context.response = context.client.get(f"/api/v1/eval/runs/compare?a={a}&b={b}")


@then("dostaje różnice mierników i listę przypadków, które zmieniły wynik")
def differences(context: Context) -> None:
    """The metric pair and the changed case are there.

    Args:
        context: the behave context.

    Features:
        US-OBS-06, F-28
    """
    body = context.response.json()
    assert body["metrics"]["macro_f1"] == {"a": 0.5, "b": 0.9}
    assert body["changed_cases"] == [{"case_id": "c1", "a": "confirmed", "b": "false"}]
