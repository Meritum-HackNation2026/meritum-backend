"""Steps for failed hand-offs: 503 with escalation.not_saved (moderation.feature)."""

from http import HTTPStatus
from typing import override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from features.steps.escalation import CLAIMS, RESULT
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState

from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.settings import Settings


class NonSavingWorker(InMemoryJobQueue):
    """Finished check ``chk-1``; every escalate_claim job ends in ERROR."""

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        if workflow_id == RESULT.check_id:
            output = CheckOutput(result=RESULT)
            dump = output.model_dump(mode="json")
            return JobState(workflow_id=workflow_id, status="SUCCESS", output=dump)
        if await super().state(workflow_id) is None:
            return None
        return JobState(workflow_id=workflow_id, status="ERROR", output=None)


@given("repozytorium spraw moderatora nie przyjmuje zapisu")
def cases_do_not_save(context: Context) -> None:
    """The worker cannot persist a case; the check is still finished.

    Args:
        context: the behave context; gets ``client`` and ``worker``.

    Features:
        US-MOD-03, US-MOD-06, F-24, backend#80
    """
    app = create_app(Settings(database_url="postgresql://x:x@127.0.0.1:1/x"))
    context.worker = NonSavingWorker()
    app.dependency_overrides[get_jobs] = lambda: context.worker
    context.client = TestClient(app)


@when("obywatel przekazuje sprawdzenie moderatorom albo zgłasza błąd")
def escalate_or_dispute(context: Context) -> None:
    """Try escalate on claim 0, then dispute on claim 1.

    Args:
        context: the behave context; gets ``responses``.

    Features:
        US-MOD-03, US-MOD-06, F-24, backend#80
    """
    client = context.client
    context.responses = [
        client.post(f"{CLAIMS}/0/escalate"),
        client.post(f"{CLAIMS}/1/dispute", json={"justification": "Błąd werdyktu."}),
    ]


@then('API odpowiada 503 z kluczem "escalation.not_saved"')
def not_saved_key(context: Context) -> None:
    """Both hand-offs get 503 and the not_saved copy key.

    Args:
        context: the behave context with ``responses``.

    Features:
        US-MOD-03, US-MOD-06, F-24, backend#80
    """
    for response in context.responses:
        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert response.json()["message_key"] == "escalation.not_saved"


@then("odpowiedź nie zawiera numeru sprawy")
def no_case_number(context: Context) -> None:
    """Escalation stays recommended with no case_id.

    Args:
        context: the behave context with ``responses``.

    Features:
        US-MOD-03, US-MOD-06, F-24, backend#80
    """
    for response in context.responses:
        body = response.json()
        assert body["escalation"] == {"state": "recommended", "case_id": None}
