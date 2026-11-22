"""Steps for /usun-moje-dane on Discord (security.feature).

Features:
    US-BEZ-05, US-BEZ-06, F-20
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from behave import given, then, when
from behave.runner import Context
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient
from meritum_core.checks.contracts import CheckRecord
from meritum_core.jobs.fakes import InMemoryJobQueue
from meritum_core.observability import AppRepositories
from pydantic import SecretStr

from meritum_backend.channels import channel_user_hash
from meritum_backend.discord.constants import (
    CHANNEL_USER,
    DELETE_MY_DATA,
    DELETED,
    EPHEMERAL,
)
from meritum_backend.jobs.api import get_jobs
from meritum_backend.limits import CheckGate, LimitSettings, get_check_gate
from meritum_backend.limits.adapters import FixedPendingChecks, MemoryRateCounter
from meritum_backend.main import create_app
from meritum_backend.settings import Settings, get_settings

_KEY = Ed25519PrivateKey.generate()
_PUBLIC = _KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
_DISCORD_USER = "1234567890"


async def _seed_discord_checks(
    repos: AppRepositories, hashed: str, *, count: int = 2
) -> None:
    now = datetime.now(UTC)
    for i in range(count):
        await repos.records.save(
            CheckRecord(
                check_id=f"dc_{i}",
                session_id=hashed,
                channel="discord",
                channel_user_hash=hashed,
                received_at=now,
                answered_at=now,
                question_masked="Czy to prawda?",
                status="done",
                verdicts=["insufficient_evidence"],
                source_ids=[],
                corpus_version="behave",
                models=[],
                retention_until=now + timedelta(days=30),
            )
        )


@given("użytkownik Discorda ma 2 sprawdzenia")
def discord_user_has_checks(context: Context) -> None:
    """Two check records for one Discord user hash.

    Features:
        US-BEZ-05, US-BEZ-06, F-20
    """
    settings = Settings(discord_public_key=_PUBLIC, channel_hash_salt=SecretStr("s"))
    context.jobs = InMemoryJobQueue()
    app = create_app(settings)
    context.repos = app.state.repositories
    salt = settings.channel_hash_salt
    assert salt is not None
    hashed = channel_user_hash("discord", _DISCORD_USER, salt)
    asyncio.run(_seed_discord_checks(context.repos, hashed))
    context.hashed = hashed
    gate = CheckGate(MemoryRateCounter(), FixedPendingChecks(), LimitSettings())
    app.dependency_overrides |= {
        get_settings: lambda: settings,
        get_jobs: lambda: context.jobs,
        get_check_gate: lambda: gate,
    }
    context.use_ready_probe(app)
    context.client = TestClient(app)


def _signed_delete(context: Context) -> dict[str, Any]:
    payload = {
        "type": 2,
        "application_id": "app",
        "token": "tok",
        "member": {"user": {"id": _DISCORD_USER}},
        "data": {"name": DELETE_MY_DATA},
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


@when("wysyła polecenie /usun-moje-dane")
def sends_delete(context: Context) -> None:
    """The signed interaction hits POST /api/v1/discord/interactions.

    Features:
        US-BEZ-05, US-BEZ-06, F-20
    """
    context.answer = _signed_delete(context)


@then(
    "zapisy z jego skrótem z solą są usunięte, a bot potwierdza to wiadomością"
    " widoczną tylko dla niego"
)
def checks_gone_and_confirmed(context: Context) -> None:
    """Records for the hash are gone and the reply is ephemeral Polish text.

    Features:
        US-BEZ-05, US-BEZ-06, F-20
    """
    assert (
        asyncio.run(context.repos.records.list_for(CHANNEL_USER, context.hashed)) == []
    )
    assert context.answer == {
        "type": 4,
        "data": {"content": DELETED, "flags": EPHEMERAL},
    }
