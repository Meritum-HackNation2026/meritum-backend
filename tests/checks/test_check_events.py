import json
from collections.abc import Callable
from typing import override

from fastapi.testclient import TestClient
from meritum_core.checks import AnalysisStatus, AnalysisStep, CheckResult
from meritum_core.checks.contracts import ClaimResult
from meritum_core.jobs.constants import CONTRACT_VERSION, PROGRESS_KEY
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

type MakeClient = Callable[[InMemoryJobQueue], TestClient]

RESULT = CheckResult(
    check_id="wf-1",
    status="out_of_scope",
    message="To nie jest pytanie o informację.",
    corpus_version="test",
)

ANSWER = RESULT.model_copy(update={"message": "Zapytaj o konkretną informację."})
VERDICT = CheckResult(
    check_id="wf-1",
    status="done",
    claims=[
        ClaimResult(
            claim="We Włoszech odbył się strajk generalny.",
            verdict="insufficient_evidence",
            explanation="Źródła w korpusie nie opisują takiego strajku.",
            unresolved="Data i zasięg strajku.",
        )
    ],
    limitations=["Korpus obejmuje tylko źródła polskie."],
    corpus_version="test",
)


class RunningJobs(InMemoryJobQueue):
    """Reports every job as a running workflow."""

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        return JobState(workflow_id=workflow_id, status="PENDING")


class FinishedJobs(InMemoryJobQueue):
    """Reports every job as finished with RESULT in the workflow output."""

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        output = CheckOutput(result=RESULT).model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


class FinishedWithAnswerJobs(InMemoryJobQueue):
    """Reports every job as finished with ANSWER in the workflow output."""

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        output = CheckOutput(result=ANSWER).model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


class PingJobs(InMemoryJobQueue):
    """Reports every job as a finished ping."""

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        output = {"contract_version": CONTRACT_VERSION, "message": "pong"}
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


def steps(**states: str) -> list[AnalysisStep]:
    return [
        AnalysisStep.model_validate({"code": c, "status": s}) for c, s in states.items()
    ]


def events(client: TestClient, check_id: str = "wf-1") -> list[AnalysisStatus]:
    with client.stream("GET", f"/api/v1/checks/{check_id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = list(response.iter_lines())
    return [
        AnalysisStatus.model_validate(json.loads(line.removeprefix("data: ")))
        for line in lines
        if line.startswith("data: ")
    ]


def test_unknown_check_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/checks/nope/events").status_code == 404


def test_another_workflow_is_not_a_check(make_client: MakeClient) -> None:
    assert make_client(PingJobs()).get("/api/v1/checks/wf-1/events").status_code == 404


def test_each_progress_value_becomes_one_event(make_client: MakeClient) -> None:
    jobs = RunningJobs()
    first = steps(receive="done", fetch_url="skipped", search_corpus="active")
    second = steps(receive="done", search_corpus="active", search_web="active")
    for value in (first, second):
        jobs.publish("wf-1", PROGRESS_KEY, AnalysisStatus(check_id="wf-1", steps=value))
    received = events(make_client(jobs))
    assert [e.steps for e in received] == [first, second]


def test_a_result_before_citations_are_verified_is_withheld(
    make_client: MakeClient,
) -> None:
    jobs = RunningJobs()
    early = steps(receive="done", verify_citations="active", write_answer="active")
    jobs.publish(
        "wf-1",
        PROGRESS_KEY,
        AnalysisStatus(check_id="wf-1", steps=early, result=VERDICT),
    )
    assert events(make_client(jobs))[0].result is None


def test_a_result_after_citations_are_verified_is_sent(make_client: MakeClient) -> None:
    jobs = RunningJobs()
    verified = steps(receive="done", verify_citations="done", write_answer="active")
    jobs.publish(
        "wf-1",
        PROGRESS_KEY,
        AnalysisStatus(check_id="wf-1", steps=verified, result=RESULT),
    )
    received = events(make_client(jobs))
    assert [e.result for e in received] == [RESULT]


def test_finished_check_ends_with_the_full_result_from_the_output(
    make_client: MakeClient,
) -> None:
    jobs = FinishedJobs()
    last = steps(receive="done", verify_citations="skipped", save_record="done")
    jobs.publish("wf-1", PROGRESS_KEY, AnalysisStatus(check_id="wf-1", steps=last))
    received = events(make_client(jobs))
    assert len(received) == 2
    assert received[-1].steps == last
    assert received[-1].result == RESULT


def test_reconnecting_replays_the_current_state(make_client: MakeClient) -> None:
    jobs = RunningJobs()
    value = steps(receive="done", search_corpus="active")
    jobs.publish("wf-1", PROGRESS_KEY, AnalysisStatus(check_id="wf-1", steps=value))
    client = make_client(jobs)
    assert [e.steps for e in events(client)] == [value]
    later = steps(receive="done", search_corpus="done", assess_evidence="active")
    jobs.publish("wf-1", PROGRESS_KEY, AnalysisStatus(check_id="wf-1", steps=later))
    assert events(client)[-1].steps == later


def test_openapi_documents_the_event_stream(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    ok = paths["/api/v1/checks/{check_id}/events"]["get"]["responses"]["200"]
    assert "text/event-stream" in ok["content"]


def test_the_output_replaces_a_draft_answer_at_the_end(make_client: MakeClient) -> None:
    jobs = FinishedWithAnswerJobs()
    verified = steps(receive="done", verify_citations="done", write_answer="active")
    jobs.publish(
        "wf-1",
        PROGRESS_KEY,
        AnalysisStatus(check_id="wf-1", steps=verified, result=RESULT),
    )
    received = events(make_client(jobs))
    assert received[-1].result == ANSWER


def test_a_poll_withholds_a_result_before_citations_are_verified(
    make_client: MakeClient,
) -> None:
    jobs = RunningJobs()
    early = steps(receive="done", verify_citations="active", write_answer="active")
    jobs.publish(
        "wf-1",
        PROGRESS_KEY,
        AnalysisStatus(check_id="wf-1", steps=early, result=VERDICT),
    )
    assert make_client(jobs).get("/api/v1/checks/wf-1").json()["result"] is None


def test_a_message_without_verdicts_is_sent_before_verification(
    make_client: MakeClient,
) -> None:
    jobs = RunningJobs()
    value = steps(receive="done", extract_claims="done", write_answer="done")
    jobs.publish(
        "wf-1",
        PROGRESS_KEY,
        AnalysisStatus(check_id="wf-1", steps=value, result=RESULT),
    )
    assert events(make_client(jobs))[0].result == RESULT
