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
from tests.discord.fakes import flat

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.checks.api import get_records, get_result_cache
from meritum_backend.discord import Message, reply_message
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

EMBED_LIMIT = 6000  # Discord: characters over one embed
FIELD_LIMIT = 1024  # Discord: characters of a field value
TWO_CLAIMS = 2  # the fake worker returns two claims
_KEY = Ed25519PrivateKey.generate()
_PUBLIC = _KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


class _Discord:
    def __init__(self) -> None:
        self.sent: list[tuple[Message, bool]] = []

    async def edit_original(
        self, application_id: str, token: str, message: Message, *, public: bool
    ) -> None:
        del application_id, token
        self.sent.append((message, public))


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
    options = [{"name": "tekst", "value": context.claim_text}]
    if getattr(context, "public", None) is not None:
        options.append({"name": "publiczne", "value": context.public})
    payload = {
        "type": 2,
        "application_id": "app",
        "token": "tok",
        "member": {"user": {"id": "1234567890"}},
        "data": {
            "name": "sprawdz",
            "options": options,
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
def _gets_result(context: Context) -> None:
    context.jobs.finished = True
    context.answer = _command(context)
    assert context.jobs.enqueued[0].payload.request.channel == "discord"


@then(
    "bot podmienia odpowiedź na jedną wiadomość: z informacją, że odpowiada system AI,"
    " i osadzeniem z werdyktem, najważniejszym cytatem ze źródłem i datą oraz siłą"
    " podstawy dla każdego twierdzenia"
)
def _one_message(context: Context) -> None:
    assert len(context.discord.sent) == 1
    message, _ = context.discord.sent[0]
    assert "systemem AI" in message["content"]
    fields = message["embeds"][0]["fields"]
    assert len(fields) == TWO_CLAIMS
    assert all(f["name"].startswith("Fałszywe: ") for f in fields)
    assert all(
        "„" in f["value"]
        and "(Urząd Miasta, " in f["value"]
        and "Siła podstawy" in f["value"]
        for f in fields
    )


@then(
    'pod wiadomością jest przycisk-link "Pełna karta" do wyniku, a w treści nie ma'
    " surowego adresu"
)
def _button(context: Context) -> None:
    message, _ = context.discord.sent[0]
    check_id = context.jobs.enqueued[0].workflow_id
    button = message["components"][0]["components"][0]
    assert (button["style"], button["label"]) == (5, "Pełna karta")
    assert button["url"].endswith(f"/sprawdzenie/{check_id}")
    assert "http" not in flat(message)


@given("użytkownik wywołuje /sprawdz z opcją publiczne: True")
def _public(context: Context) -> None:
    _app(context, "Ziemia jest płaska")
    context.public = True


@then("odpowiedź jest widoczna dla wszystkich na kanale")
def _visible(context: Context) -> None:
    assert context.answer == {"type": DEFERRED, "data": {}}
    assert context.discord.sent[0][1] is True


@then("bez tej opcji odpowiedź zostaje efemeryczna")
def _ephemeral(context: Context) -> None:
    context.public = None
    context.discord.sent.clear()
    context.answer = _command(context)
    assert context.answer == {"type": DEFERRED, "data": {"flags": EPHEMERAL}}
    assert context.discord.sent[0][1] is False


@given("wynik nie mieści się w limitach Discorda")
def _long_reply(context: Context) -> None:
    fragment = "Cytat " + "z" * 590
    claims = [
        claim_result("Twierdzenie numer " + str(i) + "." * 200, fragment)
        for i in range(12)
    ]
    context.result = check_result("c1", claims)


@when("bot buduje odpowiedź")
def _builds(context: Context) -> None:
    context.message = reply_message(
        context.result, "https://x.pl/c", first_contact=True
    )


@then("osadzenie ma razem najwyżej 6000 znaków, a bot skraca cytaty, nie twierdzenia")
def _within_limits(context: Context) -> None:
    (embed,) = context.message["embeds"]
    total = len(embed["title"]) + sum(
        len(f["name"]) + len(f["value"]) for f in embed["fields"]
    )
    assert total <= EMBED_LIMIT
    assert len(embed["fields"]) == len(context.result.claims)
    assert all("Twierdzenie numer" in f["name"] for f in embed["fields"])
    assert all(len(f["value"]) <= FIELD_LIMIT for f in embed["fields"])
    assert "…" in embed["fields"][0]["value"]


@given("sprawdzenie trwa dłużej niż 3 s")
def _slow_check(context: Context) -> None:
    _app(context, "Czy Wrocław był jedynym miastem z darmową komunikacją?")


@when("Discord czeka na odpowiedź na interakcję")
def _waits(context: Context) -> None:
    context.jobs.finished = True
    context.jobs.reads_left = 1  # the first poll sees it running, the next done
    context.answer = _command(context)


@then("bot odpowiada odroczoną odpowiedzią, a wynik wstawia w jej miejsce")
def _deferred(context: Context) -> None:
    assert context.answer == {"type": DEFERRED, "data": {"flags": EPHEMERAL}}
    assert len(context.discord.sent) == 1
