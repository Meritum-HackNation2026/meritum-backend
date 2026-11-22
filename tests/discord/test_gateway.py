import asyncio
from unittest.mock import AsyncMock, MagicMock

from meritum_core.checks.fakes import InMemoryCheckRecordRepository
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.security import PiiGateSettings, build_pii_gate
from pydantic import SecretStr
from tests.checks.cache_fakes import RESULT, FinishedWorker
from tests.checks.conftest import OFFLINE_DB
from tests.conftest import MakeProbe, worker_report

import discord
from meritum_backend.checks.adapters import MemoryResultCache
from meritum_backend.discord.api import Ports
from meritum_backend.discord.constants import ERRORS
from meritum_backend.discord.gateway import (
    GatewayHandler,
    Incoming,
    MeritumClient,
    incoming_from,
    run,
    strip_mention,
)
from meritum_backend.limits import CheckGate, LimitSettings
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.settings import Settings


def _setup(
    make_probe: MakeProbe, jobs: FinishedWorker
) -> tuple[GatewayHandler, list[str]]:
    settings = Settings(channel_hash_salt=SecretStr("salt"), database_url=OFFLINE_DB)
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    probe = make_probe(InMemoryJobQueue(), report=worker_report())
    ports = Ports(
        jobs,
        gate,
        build_pii_gate(PiiGateSettings()),
        probe,
        MemoryResultCache(),
        InMemoryCheckRecordRepository(),
        settings,
    )
    return GatewayHandler(ports), []


def _incoming(sent: list[str], text: str, message_id: str = "m1") -> Incoming:
    async def reply(content: str) -> None:  # ruff: ignore[unused-async] -- the Incoming.reply type
        sent.append(content)

    return Incoming(message_id=message_id, user_id="1234567890", text=text, reply=reply)


def test_message_starts_the_web_check_and_replies_in_conversation(
    make_probe: MakeProbe,
) -> None:
    jobs = FinishedWorker()
    handler, sent = _setup(make_probe, jobs)
    asyncio.run(handler.handle(_incoming(sent, "https://example.pl/artykul")))
    assert '"channel":"discord"' in jobs.enqueued[0].payload.model_dump_json()
    assert len(sent) == 1 + len(RESULT.claims)
    assert sent[0].startswith("Jestem botem Meritum, systemem AI.")
    assert f"/sprawdzenie/{jobs.checks()[0]}" in sent[0]


def test_redelivered_message_is_answered_once(make_probe: MakeProbe) -> None:
    jobs = FinishedWorker()
    handler, sent = _setup(make_probe, jobs)
    asyncio.run(handler.handle(_incoming(sent, "Ziemia jest płaska")))
    count = len(sent)
    asyncio.run(handler.handle(_incoming(sent, "Ziemia jest płaska")))
    assert len(sent) == count
    assert len(jobs.checks()) == 1


def test_empty_message_gets_the_hint_and_starts_nothing(
    make_probe: MakeProbe,
) -> None:
    jobs = FinishedWorker()
    handler, sent = _setup(make_probe, jobs)
    asyncio.run(handler.handle(_incoming(sent, "")))
    assert sent == [ERRORS["errors.empty"]]
    assert not jobs.enqueued


def test_seen_ids_are_bounded(make_probe: MakeProbe) -> None:
    handler, sent = _setup(make_probe, FinishedWorker())
    handler = GatewayHandler(handler.ports, remember=2)
    for n in range(3):
        asyncio.run(handler.handle(_incoming(sent, "", f"m{n}")))
    sent.clear()
    asyncio.run(handler.handle(_incoming(sent, "", "m0")))  # forgotten, answered again
    assert sent == [ERRORS["errors.empty"]]


def test_strip_mention_removes_only_the_bots_mention() -> None:
    text = "<@42> sprawdź <@!42> to <@7> https://x.pl"
    assert strip_mention(text, 42) == "sprawdź  to <@7> https://x.pl"


def _message(content: str, mentions: list[int], *, guild: bool) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.author = MagicMock(bot=False, id=7)
    message.id = 99
    message.content = content
    message.guild = MagicMock() if guild else None
    message.mentions = [MagicMock(id=i) for i in mentions]
    message.reply = AsyncMock()
    message.channel = MagicMock(send=AsyncMock())
    return message


def test_server_message_needs_a_mention_and_is_answered_as_a_reply() -> None:
    bot = MagicMock(id=42)
    assert incoming_from(_message("hej", [], guild=True), bot) is None
    message = _message("<@42> https://x.pl/a", [42], guild=True)
    incoming = incoming_from(message, bot)
    assert incoming is not None
    assert (incoming.text, incoming.user_id) == ("https://x.pl/a", "7")
    asyncio.run(incoming.reply("wynik"))
    message.reply.assert_awaited_once_with("wynik", mention_author=False)


def test_direct_message_is_answered_in_the_conversation() -> None:
    message = _message("Ziemia jest płaska", [], guild=False)
    incoming = incoming_from(message, MagicMock(id=42))
    assert incoming is not None
    asyncio.run(incoming.reply("wynik"))
    message.channel.send.assert_awaited_once_with("wynik")


def test_bots_are_ignored() -> None:
    message = _message("<@42> x", [42], guild=True)
    message.author.bot = True
    assert incoming_from(message, MagicMock(id=42)) is None


def test_client_asks_for_no_privileged_intent() -> None:
    client = MeritumClient(GatewayHandler(MagicMock()))
    assert not client.intents.message_content
    assert client.intents.dm_messages
    assert client.intents.guild_messages
    assert not client.intents.members


def test_gateway_without_token_exits_with_1() -> None:
    assert asyncio.run(run(Settings(discord_bot_token=None))) == 1
