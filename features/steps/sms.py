"""Steps of the SMS channel (channels.feature) with a fake gateway.

The app runs on core's in-memory repositories and a JobQueue that finishes every
check at once; the fake gateway records the replies instead of sending them.
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import override

from behave import given, then, when
from behave.runner import Context
from fastapi.testclient import TestClient
from meritum_core.checks import CheckResult
from meritum_core.checks.contracts import CheckRecord, ClaimResult
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from meritum_core.observability import build_app_repositories
from meritum_core.shared.database import DatabaseSettings
from pydantic import SecretStr

from meritum_backend.jobs.api import get_jobs
from meritum_backend.main import create_app
from meritum_backend.privacy import get_eraser
from meritum_backend.settings import Settings, get_settings
from meritum_backend.sms.api import get_records, get_sms
from meritum_backend.sms.constants import AI_NOTICE, UCS2_LIMIT
from meritum_backend.sms.identity import sender_hash

KEY = "behave-signing-key"
SALT = SecretStr("behave-salt")
SENDER = "+48600700800"
T0 = datetime(2026, 11, 21, 12, tzinfo=UTC)
CLAIM = "Wczoraj w Gdańsku wyłączono wszystkie bankomaty."


class _FakeGateway:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, phone_number: str, text: str) -> str:
        self.sent.append((phone_number, text))
        return str(len(self.sent))


class _FinishedJobs(InMemoryJobQueue):
    """Reports every check as finished with a not verifiable main claim."""

    def __init__(self) -> None:
        super().__init__()
        self.finished = False

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        known = await super().state(workflow_id)
        if known is None or not self.finished:
            return known
        result = CheckResult(
            check_id=workflow_id,
            status="done",
            claims=[
                ClaimResult(
                    claim=CLAIM,
                    verdict="not_verifiable",
                    explanation="To przewidywanie, nie fakt.",
                )
            ],
            limitations=["Korpus obejmuje tylko źródła polskie."],
            corpus_version="test",
        )
        output = CheckOutput(result=result).model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=output)


def _app(context: Context) -> None:
    settings = Settings(
        sms_gateway_webhook_signing_key=SecretStr(KEY), channel_hash_salt=SALT
    )
    context.jobs = _FinishedJobs()
    context.gateway = _FakeGateway()
    context.repositories = build_app_repositories(DatabaseSettings())
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_jobs] = lambda: context.jobs
    app.dependency_overrides[get_sms] = lambda: context.gateway
    app.dependency_overrides[get_records] = lambda: context.repositories.records
    app.dependency_overrides[get_eraser] = lambda: context.repositories.eraser
    context.client = TestClient(app)


def _receive(context: Context, text: str) -> None:
    body = json.dumps(
        {
            "deviceId": "dev1",
            "event": "sms:received",
            "id": f"e{len(context.jobs.enqueued)}",
            "payload": {"message": text, "sender": SENDER},
        }
    ).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(KEY.encode(), body + stamp.encode(), hashlib.sha256)
    headers = {"X-Signature": signature.hexdigest(), "X-Timestamp": stamp}
    context.response = context.client.post(
        "/api/v1/sms/webhook", content=body, headers=headers
    )


@given("webhook bramki SMS dostaje tekst z nowego numeru")
def _new_number(context: Context) -> None:
    _app(context)
    context.sms_text = CLAIM


@when("sprawdzenie się kończy")
def _check_finishes(context: Context) -> None:
    context.jobs.finished = True
    _receive(context, context.sms_text)


@then(
    "pierwsza odpowiedź mówi, że odpowiada system AI, i podaje werdykt głównego"
    " twierdzenia bez linku"
)
def _first_reply(context: Context) -> None:
    texts = [text for _, text in context.gateway.sent]
    assert texts == [AI_NOTICE, "Nie podlega weryfikacji"], texts
    assert all("http" not in text for text in texts)


@then("każdy SMS odpowiedzi ma najwyżej 70 znaków w UCS-2")
def _within_limit(context: Context) -> None:
    assert all(len(text) <= UCS2_LIMIT for _, text in context.gateway.sent)


@given("numer ma zapisane sprawdzenia")
def _number_has_checks(context: Context) -> None:
    _app(context)
    hashed = sender_hash(SENDER, SALT)
    context.hashed = hashed
    record = CheckRecord(
        check_id="sms-dev1-old",
        session_id=hashed,
        channel="sms",
        channel_user_hash=hashed,
        received_at=T0,
        answered_at=T0,
        question_masked=CLAIM,
        status="done",
        verdicts=["false"],
        source_ids=[],
        corpus_version="test",
        models=[],
        retention_until=T0 + timedelta(days=30),
    )
    asyncio.run(context.repositories.records.save(record))


@when('przychodzi SMS "{text}"')
def _sms_arrives(context: Context, text: str) -> None:
    _receive(context, text)


@then("zapisy dla skrótu z solą tego numeru są usunięte")
def _deleted(context: Context) -> None:
    left = asyncio.run(
        context.repositories.records.list_for("channel_user_hash", context.hashed)
    )
    assert context.response.json() == {"status": "deleted"}
    assert left == []
