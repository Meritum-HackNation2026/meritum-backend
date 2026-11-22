"""Fakes of the evaluation tests: a worker that finishes runs, signed-in members."""

from datetime import UTC, datetime
from typing import override
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import EvalCaseResult, EvalMetrics, EvalRun
from meritum_core.jobs.contracts import EvalRunOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.auth.adapters import FakeLogin
from meritum_backend.auth.api import get_login
from meritum_backend.auth.constants import FAKE_CODE
from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

ADMIN = "boss@example.com"
NOW = datetime(2026, 11, 22, 12, tzinfo=UTC)
CSV_HEAD = "case_id,scenario,text,expected\n"


def csv_file(count: int = 30) -> bytes:
    rows = "".join(f"c{i},A,Tekst {i},false\n" for i in range(count))
    return (CSV_HEAD + rows).encode()


class Queue(InMemoryJobQueue):
    """Reports a finished EvalRun for the ids it was given."""

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


def metrics(f1: float) -> EvalMetrics:
    return EvalMetrics(
        cases=1,
        macro_f1=f1,
        citation_coverage=None,
        citation_correctness=0.5,
        abstention=None,
        robustness=None,
        median_seconds=1,
        p95_seconds=2,
        max_seconds=3,
        input_tokens_per_check=10,
        output_tokens_per_check=5,
        cost_per_check_usd=0.01,
        cost_100_checks_usd=1,
        channel_consistency=None,
        information_loop=None,
    )


def finished(
    run_id: str, f1: float, predicted: str, case_set: str = "golden"
) -> EvalRun:
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
        case_set=case_set,  # ty: ignore[invalid-argument-type]
        case_file="cases.csv" if case_set == "user_file" else None,
        status="done",
        corpus_version="v1",
        user_id="staff:" + "a" * 32,
        started_at=NOW,
        finished_at=NOW,
        metrics=metrics(f1),
        cases=(case,),
    )


def queue() -> Queue:
    return Queue()


def app(queue: Queue) -> FastAPI:
    settings = Settings(
        database_url="postgresql://x:x@127.0.0.1:1/x",
        admin_emails=ADMIN,
        public_url="https://meritum.example",
    )
    app = create_app(settings)
    app.dependency_overrides[get_jobs] = lambda: queue
    return app


def signed_in(app: FastAPI, email: str) -> TestClient:
    app.dependency_overrides[get_login] = lambda: FakeLogin("sub", email)
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    location = client.get("/api/v1/auth/login/google").headers["location"]
    state = parse_qs(urlparse(location).query)["state"][0]
    client.get(
        "/api/v1/auth/callback/google", params={"code": FAKE_CODE, "state": state}
    )
    client.headers["X-CSRF-Token"] = client.get("/api/v1/auth/me").json()["csrf_token"]
    return client


def member(app: FastAPI, role: str | None) -> TestClient:
    if role is None:
        return signed_in(app, "nobody@example.com")
    if role == "admin":
        return signed_in(app, ADMIN)
    email = f"{role}@example.com"
    assert (
        signed_in(app, ADMIN)
        .post("/api/v1/staff", json={"email": email, "role": role})
        .is_success
    )
    return signed_in(app, email)
