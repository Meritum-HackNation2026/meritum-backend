"""Steps of the Discord commands (channels.feature) with a fake Discord client.

The app runs on in-memory fakes and a JobQueue that finishes a check when told;
the fake client records the messages instead of calling Discord.
"""

import json
from typing import Any, override

from behave import given, then, when
from behave.runner import Context
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from features.discord_support import check_result, claim_result
from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.jobs.contracts import CheckOutput
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.jobs.ports import JobState
from pydantic import SecretStr

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_records, get_result_cache
from meritum_backend.discord import MESSAGE_MAX_CHARS, reply_messages
from meritum_backend.discord.api import get_replies
from meritum_backend.discord.constants import (
    DEFERRED_CHANNEL_MESSAGE as DEFERRED,
)
from meritum_backend.discord.constants import EPHEMERAL
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

_KEY = Ed25519PrivateKey.generate()
_PUBLIC = _KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


class _Discord:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def edit_original(self, application_id: str, token: str, text: str) -> None:
        del application_id, token
        self.sent.append(("edit", text))

    async def follow_up(self, application_id: str, token: str, text: str) -> None:
        del application_id, token
        self.sent.append(("follow_up", text))


class _Worker(InMemoryJobQueue):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text
        self.finished = False
        self.reads_left = 0  # reads that still see a running check

    @override
    async def state(self, workflow_id: str) -> JobState | None:
        known = await super().state(workflow_id)
        if known is None or not self.finished or self.reads_left > 0:
            self.reads_left -= 1
            return known
        claims = [
            claim_result(
                self.text, "Bezpłatne przejazdy przysługują seniorom w wielu miastach."
            ),
            claim_result(
                "Kraków też ma darmowe przejazdy.",
                "Kraków wprowadził bezpłatne przejazdy.",
            ),
        ]
        output = CheckOutput(result=check_result(workflow_id, claims))
        dump = output.model_dump(mode="json")
        return JobState(workflow_id=workflow_id, status="SUCCESS", output=dump)


def _app(context: Context, text: str) -> None:
    settings = Settings(discord_public_key=_PUBLIC, channel_hash_salt=SecretStr("s"))
    context.jobs = _Worker(text)
    context.discord = _Discord()
    app = create_app(settings)
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    cache, records = MemoryResultCache(), InMemoryCheckRecordRepository()
    app.dependency_overrides |= {
        get_settings: lambda: settings,
        get_jobs: lambda: context.jobs,
        get_check_gate: lambda: gate,
        get_result_cache: lambda: cache,
        get_records: lambda: records,
        get_replies: lambda: context.discord,
    }
    context.use_ready_probe(app)
    context.client = TestClient(app)
    context.claim_text = text


def _command(context: Context) -> dict[str, Any]:
    payload = {
        "type": 2,
        "application_id": "app",
        "token": "tok",
        "member": {"user": {"id": "1234567890"}},
        "data": {
            "name": "sprawdz",
            "options": [{"name": "tekst", "value": context.claim_text}],
        },
    }
    body = json.dumps(payload).encode()
    stamp = "1795265000"
    headers = {
        "X-Signature-Ed25519": _KEY.sign(stamp.encode() + body).hex(),
        "X-Signature-Timestamp": stamp,
    }
    response = context.client.post(
        "/api/v1/discord/interactions", content=body, headers=headers
    )
    return response.json()


@given('użytkownik pierwszy raz wywołuje /sprawdz z tekstem "{text}"')
def _first_command(context: Context, text: str) -> None:
    _app(context, text)


@when('bot dostaje wynik sprawdzenia z kanałem "discord"')
def _getscheck_result(context: Context) -> None:
    context.jobs.finished = True
    context.answer = _command(context)
    assert context.jobs.enqueued[0].payload.request.channel == "discord"


@then(
    "pierwsza wiadomość mówi, że odpowiada system AI, i podsumowuje werdykt każdego"
    " twierdzenia z linkiem do pełnej karty wyniku"
)
def _summary(context: Context) -> None:
    kind, first = context.discord.sent[0]
    check_id = context.jobs.enqueued[0].workflow_id
    assert kind == "edit"
    assert "systemem AI" in first
    assert f"/sprawdzenie/{check_id}" in first
    assert first.count("Fałszywe: ") == len(context.discord.sent) - 1, first


@then(
    "potem bot wysyła po jednej wiadomości na twierdzenie: werdykt, jeden"
    " najważniejszy cytat albo ocenę fact-checkera ze źródłem i siłę"
)
def _perclaim_result(context: Context) -> None:
    rest = context.discord.sent[1:]
    assert [kind for kind, _ in rest] == ["follow_up", "follow_up"]
    assert all(text.startswith("Fałszywe: ") for _, text in rest)
    assert all(
        "„" in text and "(Urząd Miasta, " in text and "Siła podstawy" in text
        for _, text in rest
    )


@given("odpowiedź dla twierdzenia przekracza 2000 znaków")
def _long_reply(context: Context) -> None:
    fragment = "Cytat " + "z" * 590
    claims = [
        claim_result("Twierdzenie numer " + str(i) + "." * 480, fragment)
        for i in range(5)
    ]
    context.result = check_result("c1", claims)
    context.quote = f"„{fragment}”"


@when("bot dzieli odpowiedź na wiadomości")
def _splits(context: Context) -> None:
    context.messages = reply_messages(
        context.result, "https://x.pl/c", first_contact=True
    )


@then(
    "żadna wiadomość nie ma więcej niż 2000 znaków treści, osadzenia mają razem"
    " najwyżej 6000 znaków, a podział nie przecina cytatu"
)
def _within_limits(context: Context) -> None:
    messages = list[str](context.messages)
    assert sum(len(m) for m in messages) > MESSAGE_MAX_CHARS
    assert all(len(m) <= MESSAGE_MAX_CHARS for m in messages)
    # replies are plain content: no embeds, so the 6000-character embed limit holds
    assert all(isinstance(m, str) for m in messages)
    quoted = [m for m in messages if "„Cytat" in m]
    assert all(context.quote in m for m in quoted)


@given("sprawdzenie trwa dłużej niż 3 s")
def _slow_check(context: Context) -> None:
    _app(context, "Czy Wrocław był jedynym miastem z darmową komunikacją?")


@when("Discord czeka na odpowiedź na interakcję")
def _waits(context: Context) -> None:
    context.jobs.finished = True
    context.jobs.reads_left = 1  # the first poll sees it running, the next done
    context.answer = _command(context)


@then(
    "bot odpowiada odroczoną odpowiedzią, a wynik wysyła jako wiadomość uzupełniającą"
)
def _deferred(context: Context) -> None:
    assert context.answer == {"type": DEFERRED, "data": {"flags": EPHEMERAL}}
    kinds = [kind for kind, _ in context.discord.sent]
    assert kinds == ["edit", "follow_up", "follow_up"], kinds
