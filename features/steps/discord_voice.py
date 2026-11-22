"""Steps of the Discord voice message scenarios (channels.feature).

The Gateway handler runs on in-memory ports, a fake CDN and a worker that
finishes at once with a transcript; the conversation records the replies.
"""

import asyncio
from unittest.mock import MagicMock

from behave import given, then, when
from behave.runner import Context
from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.security import PiiGateSettings, build_pii_gate
from meritum_core.shared.blobs.adapters import MemoryBlobStore
from pydantic import SecretStr
from tests.checks.cache_fakes import RESULT, FinishedWorker
from tests.discord.fakes import flat
from tests.discord.test_voice import CDN, FakeCdn, ogg

from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.discord.api import Ports
from meritum_backend.discord.constants import TRANSCRIPT_HINT
from meritum_backend.discord.gateway import GatewayHandler, Incoming
from meritum_backend.discord.messages import Message
from meritum_backend.limits import CheckGate, LimitSettings
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.settings import Settings

_TRANSCRIPT = "Ziemia jest płaska"


def _voice(context: Context, data: bytes) -> None:
    result = RESULT.model_copy(update={"transcript": _TRANSCRIPT})
    context.jobs = FinishedWorker(result)
    context.sent = []
    context.cdn = FakeCdn(data)
    context.use_ready_probe(MagicMock(dependency_overrides={}))
    ports = Ports(
        context.jobs,
        CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings()),
        build_pii_gate(PiiGateSettings()),
        context.probe,
        MemoryResultCache(),
        InMemoryCheckRecordRepository(),
        Settings(channel_hash_salt=SecretStr("s")),
        MemoryBlobStore(),
    )
    context.gateway = GatewayHandler(ports, voice=context.cdn)


@given("użytkownik wysyła botowi wiadomość głosową OGG trwającą {seconds:d} s")
def _ogg(context: Context, seconds: int) -> None:
    _voice(context, ogg(seconds))


@given("załącznik audio w formacie, którego transkrypcja nie obsługuje")
def _unsupported(context: Context) -> None:
    _voice(context, b"to nie jest nagranie")


@when("bot ją odbiera")
@when("bot go odbiera")
def _receives(context: Context) -> None:
    async def reply(message: Message) -> None:  # ruff: ignore[unused-async] -- the Incoming.reply type
        context.sent.append(flat(message))

    incoming = Incoming("m1", "1234567890", "", reply, CDN)
    asyncio.run(context.gateway.handle(incoming))


@then("pobiera załącznik od razu i zleca sprawdzenie z audio_id")
def _downloaded(context: Context) -> None:
    assert context.cdn.urls == [CDN]
    assert '"audio_id":"' in context.jobs.enqueued[0].payload.model_dump_json()


@then(
    "odpowiedź zawiera transkrypcję z informacją, że powstała automatycznie"
    " i może mieć błędy"
)
def _transcript(context: Context) -> None:
    assert _TRANSCRIPT in context.sent[0]
    assert TRANSCRIPT_HINT in context.sent[0]


@then('odpowiada stanem "out_of_scope" z informacją, co można wysłać zamiast tego')
def _refused(context: Context) -> None:
    assert not context.jobs.enqueued
    assert "Tego nagrania nie sprawdzimy" in context.sent[0]
    assert "OGG, MP3, M4A, WAV" in context.sent[0]
