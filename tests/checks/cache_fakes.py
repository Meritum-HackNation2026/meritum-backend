"""A worker stand-in for the result cache tests: every job finishes at once."""

from pathlib import Path
from typing import override

from meritum_core.checks import CheckResult, Escalation
from meritum_core.jobs.contracts import CheckOutput, EscalateClaimOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

FIXTURE = Path(__file__).parents[2] / "features" / "fixtures" / "check_result.json"
RESULT = CheckResult.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
FAILURE = CheckResult(
    check_id="x",
    status="technical_failure",
    message="Spróbuj ponownie.",
    failure_code="provider_unavailable",
    corpus_version=RESULT.corpus_version,
)
CASE = Escalation(state="created", case_id="#S-9")


class FinishedWorker(InMemoryJobQueue):
    """`check` ends with ``result`` and ``first_case``; escalations with CASE."""

    def __init__(
        self, result: CheckResult = RESULT, first_case: Escalation | None = None
    ) -> None:
        super().__init__()
        self.result = result
        self.first_case = first_case

    def checks(self) -> list[str]:
        return [j.workflow_id for j in self.enqueued if j.spec.name == "check"]

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        job = next((j for j in self.enqueued if j.workflow_id == workflow_id), None)
        if job is None:
            return None
        if job.spec.name == "check":
            update = {"check_id": workflow_id, "escalation": self.first_case}
            output = CheckOutput(result=self.result.model_copy(update=update))
        else:
            output = EscalateClaimOutput(escalation=CASE)
        dump = output.model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=dump)
