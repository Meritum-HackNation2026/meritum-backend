"""Steps of the Discord Gateway scenarios (channels.feature) with a fake Gateway.

The handler runs on in-memory ports and a worker that finishes at once; the fake
conversation records the replies instead of calling Discord.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from behave import given, then, when
from behave.runner import Context
from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.security import PiiGateSettings, build_pii_gate
from pydantic import SecretStr
from tests.checks.cache_fakes import FinishedWorker

import discord
from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.discord.api import Ports
from meritum_backend.discord.gateway import (
    GatewayHandler,
    MeritumClient,
    incoming_from,
)
from meritum_backend.limits import CheckGate, LimitSettings
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.settings import Settings

_BOT_ID = 42


def _handler(context: Context) -> None:
    settings = Settings(channel_hash_salt=SecretStr("s"))
    context.jobs = FinishedWorker()
    context.sent = []
    context.use_ready_probe(MagicMock(dependency_overrides={}))  # marks the probe ready
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    ports = Ports(
        context.jobs,
        gate,
        build_pii_gate(PiiGateSettings()),
        context.probe,
        MemoryResultCache(),
        InMemoryCheckRecordRepository(),
        settings,
    )
    context.gateway = GatewayHandler(ports)


def _message(context: Context, content: str, *, in_server: bool) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(bot=False, id=7)
    message.id = 99
    message.content = content
    message.guild = MagicMock() if in_server else None
    message.mentions = [MagicMock(id=_BOT_ID)] if in_server else []
    message.reply = AsyncMock(side_effect=lambda text, **_: context.sent.append(text))
    message.channel = MagicMock(send=AsyncMock(side_effect=context.sent.append))
    return message


def _deliver(context: Context) -> None:
    incoming = incoming_from(context.message, MagicMock(id=_BOT_ID))
    assert incoming is not None
    asyncio.run(context.gateway.handle(incoming))


@given("użytkownik pisze do bota wiadomość prywatną z tekstem do sprawdzenia")
def _dm(context: Context) -> None:
    _handler(context)
    context.message = _message(context, "Ziemia jest płaska", in_server=False)


@when("proces Gateway ją odbiera")
def _receives(context: Context) -> None:
    _deliver(context)


@then(
    'woła to samo sprawdzenie co POST /api/v1/checks z channel "discord" i odpowiada'
    " w tej rozmowie wiadomościami z backend/007"
)
def _same_check(context: Context) -> None:
    assert '"channel":"discord"' in context.jobs.enqueued[0].payload.model_dump_json()
    assert context.message.channel.send.await_count == len(context.sent) > 1
    assert "systemem AI" in context.sent[0]
    context.message.reply.assert_not_awaited()


@given("bot jest na serwerze bez uprzywilejowanej intencji MESSAGE_CONTENT")
def _no_content_intent(context: Context) -> None:
    _handler(context)
    assert not MeritumClient(context.gateway).intents.message_content


@when("ktoś wspomina bota z linkiem do artykułu")
def _mention(context: Context) -> None:
    context.message = _message(
        context, f"<@{_BOT_ID}> https://example.pl/artykul", in_server=True
    )
    _deliver(context)


@then("bot odpowiada w wątku wynikiem sprawdzenia linku")
def _reply_with_result(context: Context) -> None:
    payload = context.jobs.enqueued[0].payload.model_dump_json()
    assert "https://example.pl/artykul" in payload
    assert context.message.reply.await_count == len(context.sent) > 1


@given("Gateway zrywa połączenie")
def _dropped(context: Context) -> None:
    _handler(context)
    context.message = _message(context, "Ziemia jest płaska", in_server=False)
    _deliver(context)
    context.answered = len(context.sent)


@when("proces wznawia sesję")
def _resumes(context: Context) -> None:
    _deliver(context)  # a resumed session replays the event


@then("nie wysyła drugi raz odpowiedzi na wiadomość, na którą już odpowiedział")
def _once(context: Context) -> None:
    assert len(context.sent) == context.answered
    assert len(context.jobs.checks()) == 1
