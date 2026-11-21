"""Starting a check from a Discord command: the web form's own POST /api/v1/checks.

Features:
    US-WTY-06, US-BEZ-06, F-03, ADR-08
"""

import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from meritum_core.checks import CheckRecordRepository
from meritum_core.checks.contracts import CheckRequest
from meritum_core.jobs.ports import JobQueue
from meritum_core.security import PiiGatePort
from pydantic import ValidationError

from meritum_backend.channels import channel_user_hash
from meritum_backend.checks import ResultCache, message_key
from meritum_backend.checks.api import start_check
from meritum_backend.discord.constants import (
    CHANNEL,
    CHANNEL_MESSAGE,
    EPHEMERAL,
    ERRORS,
    FAILURE_TEXT,
    REGION,
)
from meritum_backend.health.readiness import ReadinessProbe
from meritum_backend.limits import CheckGate, CheckRefusedError, Origin
from meritum_backend.settings import Settings


def message(text: str) -> dict[str, Any]:
    """An ephemeral channel message answering the interaction.

    Args:
        text: the message.

    Returns:
        The interaction response.

    Features:
        US-WTY-06, F-03
    """
    return {"type": CHANNEL_MESSAGE, "data": {"content": text, "flags": EPHEMERAL}}


def _refusal_text(started: JSONResponse) -> str:
    if started.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT:
        return FAILURE_TEXT
    key = json.loads(bytes(started.body)).get("message_key", "")
    return ERRORS.get(key, FAILURE_TEXT)


def user_hash(settings: Settings, user_id: str) -> str | None:
    """The salted hash start_check gives this Discord user.

    Args:
        settings: holds the hash salt.
        user_id: the Discord user id; empty when the interaction has none.

    Returns:
        The hash, or None without a user id or a salt.

    Features:
        US-WTY-06, US-BEZ-06, F-20
    """
    salt = settings.channel_hash_salt
    if salt is None or not user_id:
        return None
    return channel_user_hash(CHANNEL, user_id, salt)


@dataclass(frozen=True)
class Ports:
    """The ports POST /api/v1/checks takes, gathered for one command.

    Attributes:
        jobs: the job queue port.
        gate: the shared rate limits.
        pii: the personal-data masking gate.
        readiness: the readiness probe.
        cache: the result cache.
        records: the check records.
        settings: the app settings.

    Features:
        US-WTY-06, F-03, ADR-08
    """

    jobs: JobQueue
    gate: CheckGate
    pii: PiiGatePort
    readiness: ReadinessProbe
    cache: ResultCache
    records: CheckRecordRepository
    settings: Settings


async def start(ports: Ports, text: str, user_id: str) -> str | dict[str, Any]:
    """Run POST /api/v1/checks itself, so Discord has no verification of its own.

    Args:
        ports: what start_check takes.
        text: the text the user asked about.
        user_id: the Discord user id; start_check hashes it.

    Returns:
        The check id, or the ephemeral answer saying why it did not start.

    Features:
        US-WTY-06, US-BEZ-06, F-03, ADR-08
    """
    hashed = user_hash(ports.settings, user_id) or ""
    request = {"channel": CHANNEL, "text": text, "channel_user_id": user_id or None}
    try:
        check = CheckRequest.model_validate(request)
        started = await start_check(
            check,
            ports.jobs,
            ports.gate,
            Origin(ip=hashed, region=REGION),
            ports.pii,
            ports.readiness,
            ports.cache,
            ports.records,
            ports.settings,
        )
    except ValidationError as exc:
        return message(ERRORS.get(message_key(exc.errors()), FAILURE_TEXT))
    except CheckRefusedError as exc:
        return message(ERRORS.get(exc.refusal.message_key, FAILURE_TEXT))
    except HTTPException:
        return message(FAILURE_TEXT)
    if isinstance(started, JSONResponse):
        return message(_refusal_text(started))
    return started.check_id
