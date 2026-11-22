import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import override

import pytest
from fastapi.testclient import TestClient
from meritum_core.checks import CheckResult
from meritum_core.jobs.contracts import (
    PING,
    CheckOutput,
    EscalateClaimOutput,
    PingInput,
)
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from pydantic import JsonValue

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_result_cache
from meritum_backend.checks.cache import cache_entry
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import limiter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings

FIXTURE = Path(__file__).parents[2] / "features" / "fixtures" / "check_result.json"
RESULT = CheckResult.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
CLAIMS = "/api/v1/checks/chk-1/claims"
NOT_SAVED = {
    "escalation": {"state": "recommended", "case_id": None},
    "message_key": "escalation.not_saved",
}
CREATED = {"escalation": {"state": "created", "case_id": "#S-12"}}


class Worker(InMemoryJobQueue):
    """Finished check ``chk-1``; every other job ends as ``status`` with ``output``."""

    def __init__(self, status: str, output: dict[str, JsonValue] | None) -> None:
        super().__init__()
        self.status = status
        self.output = output

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        if workflow_id == RESULT.check_id:
            dump = CheckOutput(result=RESULT).model_dump(mode="json")
            return JobState(workflow_id=workflow_id, status="SUCCESS", output=dump)
        if await super().state(workflow_id) is None:
            return None
        return JobState(workflow_id=workflow_id, status=self.status, output=self.output)


def _client(jobs: InMemoryJobQueue) -> TestClient:
    limiter.reset()  # the counters live in the module, across tests
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    app.dependency_overrides[get_jobs] = lambda: jobs
    return TestClient(app)


def _saved(case: dict[str, dict[str, str]] = CREATED) -> Worker:
    output = EscalateClaimOutput.model_validate(case).model_dump(mode="json")
    return Worker("SUCCESS", output)


def test_escalation_asks_the_worker_for_a_recommended_click() -> None:
    worker = _saved()
    response = _client(worker).post(f"{CLAIMS}/0/escalate")
    assert response.json() == {**CREATED, "message_key": "escalation.created"}
    [job] = worker.enqueued
    assert job.spec.name == "escalate_claim"
    assert job.payload.model_dump(exclude={"contract_version"}) == {
        "check_id": "chk-1",
        "claim_index": 0,
        "reason": "recommended_clicked",
        "justification_masked": None,
    }


@pytest.mark.parametrize("route", ["escalate", "dispute"])
def test_joining_a_case_says_only_that_the_question_joined(route: str) -> None:
    joined = {"escalation": {"state": "updated", "case_id": "#S-7"}}
    response = _client(_saved(joined)).post(
        f"{CLAIMS}/1/{route}", json={"justification": "Źródło jest stare."}
    )
    key = {"escalate": "escalation.updated", "dispute": "result.report_error_done"}
    assert response.json() == {**joined, "message_key": key[route]}


def test_hand_offs_are_rate_limited() -> None:
    client = _client(_saved())
    codes = [client.post(f"{CLAIMS}/0/escalate").status_code for _ in range(11)]
    assert codes == [200] * 10 + [429]


@pytest.mark.parametrize(
    "path", ["/api/v1/checks/nope/claims/0/escalate", f"{CLAIMS}/2/escalate"]
)
def test_unknown_check_or_claim_is_404_and_starts_nothing(path: str) -> None:
    worker = _saved()
    response = _client(worker).post(path)
    assert response.json() == {"detail": "claim not found"}
    assert worker.enqueued == []


def test_a_running_check_has_no_claims_to_hand_off() -> None:
    jobs = InMemoryJobQueue()
    running = asyncio.run(jobs.enqueue(PING, PingInput()))
    response = _client(jobs).post(f"/api/v1/checks/{running}/claims/0/escalate")
    assert response.json() == {"detail": "claim not found"}
    assert len(jobs.enqueued) == 1


@pytest.mark.parametrize(
    ("status", "output"),
    [
        ("ERROR", None),
        ("CANCELLED", None),
        ("SUCCESS", {"escalation": {"state": "recommended"}}),
        ("SUCCESS", {"unexpected": True}),
    ],
)
@pytest.mark.parametrize("route", ["escalate", "dispute"])
def test_a_case_that_was_not_saved_gives_no_number(
    status: str, output: dict[str, JsonValue] | None, route: str
) -> None:
    response = _client(Worker(status, output)).post(f"{CLAIMS}/0/{route}")
    assert response.status_code == 503
    assert response.json() == NOT_SAVED


def test_a_case_not_saved_in_time_gives_no_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "meritum_backend.moderation.api._workflow.ESCALATION_WAIT_SECONDS", 0.05
    )
    response = _client(Worker("PENDING", None)).post(f"{CLAIMS}/0/escalate")
    assert response.status_code == 503
    assert response.json() == NOT_SAVED


@pytest.mark.parametrize("body", [None, {}, {"justification": "   "}])
def test_a_dispute_without_a_reason_goes_without_one(
    body: dict[str, str] | None,
) -> None:
    worker = _saved()
    response = _client(worker).post(f"{CLAIMS}/1/dispute", json=body)
    assert response.json()["message_key"] == "result.report_error_done"
    [job] = worker.enqueued
    assert job.payload.model_dump()["justification_masked"] is None


@pytest.mark.parametrize("padding", [991, 993])
def test_a_long_reason_is_masked_before_it_is_cut(padding: int) -> None:
    worker = _saved()
    body = {"justification": "a" * padding + " 600 700 800 koniec"}
    response = _client(worker).post(f"{CLAIMS}/1/dispute", json=body)
    assert response.json()["message_key"] == "result.report_error_done"
    [job] = worker.enqueued
    sent = job.payload.model_dump()["justification_masked"]
    assert len(sent) <= 1000
    assert "600" not in sent
    assert "70" not in sent


def test_a_reason_that_is_not_text_is_refused_without_echo() -> None:
    worker = _saved()
    body = {"justification": ["600 700 800"]}
    response = _client(worker).post(f"{CLAIMS}/1/dispute", json=body)
    assert response.status_code == 422
    assert "600" not in response.text
    assert worker.enqueued == []


def test_a_masked_reason_never_outgrows_the_contract() -> None:
    worker = _saved()
    reason = "a@b.pl " * 142  # 994 characters; each e-mail grows into "[e-mail]"
    response = _client(worker).post(
        f"{CLAIMS}/1/dispute", json={"justification": reason}
    )
    assert response.json()["message_key"] == "result.report_error_done"
    [job] = worker.enqueued
    sent = job.payload.model_dump()["justification_masked"]
    assert len(sent) <= 1000
    assert sent.rstrip().endswith("[e-mail]")  # cut before a marker, never inside one


def test_a_reason_over_4000_characters_is_too_long() -> None:
    worker = _saved()
    client = _client(worker)
    phone = "600 700 800 "
    ok = client.post(f"{CLAIMS}/1/dispute", json={"justification": "x" * 4000})
    assert ok.json()["message_key"] == "result.report_error_done"
    body = {"justification": phone + "x" * 3989}
    response = client.post(f"{CLAIMS}/1/dispute", json=body)
    assert response.status_code == 422
    assert response.json() == {"message_key": "errors.too_long"}
    assert len(worker.enqueued) == 1


class _Announcer:
    def __init__(self) -> None:
        self.cases: list[str] = []

    async def announce(self, case_id: str) -> None:
        self.cases.append(case_id)


@pytest.mark.parametrize("route", ["escalate", "dispute"])
def test_a_saved_case_is_announced_to_the_moderators(route: str) -> None:
    client = _client(_saved())
    client.app.state.announcer = announcer = _Announcer()  # ty: ignore[missing-attribute]

    client.post(f"{CLAIMS}/0/{route}")

    assert announcer.cases == ["#S-12"]


def test_a_case_that_was_not_saved_is_not_announced() -> None:
    client = _client(Worker("ERROR", None))
    client.app.state.announcer = announcer = _Announcer()  # ty: ignore[missing-attribute]

    client.post(f"{CLAIMS}/0/escalate")

    assert announcer.cases == []


@pytest.mark.parametrize("route", ["escalate", "dispute"])
def test_a_result_served_from_the_cache_can_be_handed_off(route: str) -> None:
    cache = MemoryResultCache()
    entry = cache_entry(RESULT, datetime.now(UTC))
    assert entry is not None
    asyncio.run(
        cache.link("hit-1", "key", entry)
    )  # a hit has no workflow, only an entry
    worker = _saved()
    client = _client(worker)
    client.app.dependency_overrides[get_result_cache] = lambda: cache  # ty: ignore[missing-attribute]
    response = client.post(f"/api/v1/checks/hit-1/claims/0/{route}")
    assert response.status_code == 200
    assert [j.payload.model_dump()["check_id"] for j in worker.enqueued] == ["hit-1"]
    assert (
        client.post(
            f"/api/v1/checks/hit-1/claims/{len(entry.claims)}/{route}"
        ).status_code
        == 404
    )
