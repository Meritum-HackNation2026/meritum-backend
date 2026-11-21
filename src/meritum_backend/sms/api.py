"""POST /api/v1/sms/webhook: SMS received by the sms-gate.app gateway.

The gateway signs every call (HMAC-SHA256, ±5 min) and retries for about two days
until it gets a 2xx, so the answer comes at once and the work goes to the job
queue: a check (deduplicated by the event's ``deviceId`` + ``id``) or, for
``USUN``, the deletion of the number's checks. Without a signing key or gateway
credentials the endpoint does not exist (404).

Features:
    US-WTY-07, US-BEZ-06, US-BEZ-07, F-32, F-21, F-20, ADR-08
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from meritum_core.checks import CheckRequest
from meritum_core.checks.ports import CheckRecordRepository
from meritum_core.jobs.contracts import CHECK, CheckInput
from meritum_core.jobs.ports import JobQueue
from meritum_core.observability import SubjectEraser
from meritum_core.security import PiiGatePort
from pydantic import BaseModel, SecretStr, ValidationError

from meritum_backend.channels import channel_user_hash
from meritum_backend.checks import masked
from meritum_backend.checks.api import PiiGate
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import CheckGate, Gate, Origin
from meritum_backend.privacy import delete_subject, get_eraser
from meritum_backend.settings import Settings, get_settings
from meritum_backend.sms.constants import (
    CHANNEL,
    CHANNEL_USER,
    DELETE_COMMAND,
    DIACRITICS,
    SIGNATURE_HEADER,
    SMS_RECEIVED,
    SMS_REGION,
    TEXT_MAX_CHARS,
    TIMESTAMP_HEADER,
    TOO_LONG_TEXT,
)
from meritum_backend.sms.delivery import reply_when_done
from meritum_backend.sms.models import GatewayEvent
from meritum_backend.sms.numbers import e164
from meritum_backend.sms.ports import SmsSender
from meritum_backend.sms.replies import one_sms
from meritum_backend.sms.signature import signature_is_valid

router = APIRouter(prefix="/api/v1/sms", tags=["sms"])


class Received(BaseModel):
    """202 answer to the gateway (it only looks at the status code).

    Attributes:
        status: accepted (a check started), duplicate (a retried event),
            deleted (USUN), rejected (text not checkable), refused (over a
            limit or the queue is full; no reply, so no SMS cost) or ignored.

    Features:
        US-WTY-07, F-32
    """

    status: Literal[
        "accepted", "duplicate", "deleted", "rejected", "refused", "ignored"
    ]


def get_sms(request: Request) -> SmsSender | None:
    """The gateway sender the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The sender, or None when the gateway is not configured.

    Features:
        US-WTY-07, F-32
    """
    return request.app.state.sms


def get_records(request: Request) -> CheckRecordRepository:
    """The check records the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The repository that tells whether a number wrote before.

    Features:
        US-WTY-07, F-32
    """
    return request.app.state.repositories.records


Sms = Annotated[SmsSender | None, Depends(get_sms)]
Records = Annotated[CheckRecordRepository, Depends(get_records)]
Eraser = Annotated[SubjectEraser, Depends(get_eraser)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _secret(value: SecretStr | None) -> str:
    return value.get_secret_value() if value is not None else ""


async def _signed_event(request: Request, key: str) -> GatewayEvent:
    body = await request.body()
    headers = request.headers
    signature = headers.get(SIGNATURE_HEADER, "")
    stamp = headers.get(TIMESTAMP_HEADER, "")
    if not signature_is_valid(key, signature, stamp, body, time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid request signature")
    try:
        return GatewayEvent.model_validate_json(body)
    except ValidationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad event") from None


async def _check_input(text: str, hashed: str, pii: PiiGatePort) -> CheckInput:
    request = CheckRequest(channel=CHANNEL, text=text)
    return CheckInput(
        request=await masked(request, pii),
        session_id=hashed,
        channel_user_hash=hashed,
        received_at=datetime.now(UTC),
    )


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def webhook(  # ruff: ignore[too-many-arguments]  # FastAPI dependencies, one per port
    request: Request,
    *,
    settings: AppSettings,
    jobs: Jobs,
    sms: Sms,
    records: Records,
    eraser: Eraser,
    pii: PiiGate,
    gate: Gate,
    background: BackgroundTasks,
) -> Received:
    """Take one gateway event: start a check, delete on USUN, or drop it.

    Args:
        request: the signed webhook call.
        settings: the signing key, the gateway number, the salt, GSM-7 mode.
        jobs: the job queue port.
        sms: the gateway sender.
        records: check records; none for the number means first contact.
        eraser: deletes the number's checks on USUN.
        pii: masks personal data in the text before it is queued.
        gate: the shared rate limits and the pending-checks threshold.
        background: runs the reply after the answer.

    Returns:
        What happened to the event.

    Raises:
        HTTPException: 404 when the gateway is not configured, 401 for a bad or
            stale signature, 400 for a malformed event, 503 without a hash salt.

    Features:
        US-WTY-07, US-BEZ-06, US-BEZ-07, F-32, F-21, F-20
    """
    key = _secret(settings.sms_gateway_webhook_signing_key)
    if not key or sms is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    event = await _signed_event(request, key)
    received = event.payload
    if event.event != SMS_RECEIVED or received is None:
        return Received(status="ignored")
    sender = e164(received.sender)
    # the gateway texting itself (live test) must not start a reply loop
    if sender == e164(settings.sms_gateway_number or ""):
        return Received(status="ignored")
    salt = settings.channel_hash_salt
    if salt is None:  # the settings already turn an empty salt into None
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no hash salt")
    hashed = channel_user_hash(CHANNEL, sender, salt)
    if received.message.strip().upper().translate(DIACRITICS) == DELETE_COMMAND:
        await delete_subject(CHANNEL_USER, hashed, eraser, jobs)
        return Received(status="deleted")
    check_id = f"{CHANNEL}-{event.device_id}-{event.id}"
    if await jobs.state(check_id) is not None:
        return Received(status="duplicate")
    sending = _Sending(
        jobs, sms, records, pii, gate, background, sender, settings.sms_gsm7
    )
    return await _start_check(sending, check_id, received.message, hashed)


@dataclass(frozen=True)
class _Sending:
    jobs: JobQueue
    sms: SmsSender
    records: CheckRecordRepository
    pii: PiiGatePort
    gate: CheckGate
    background: BackgroundTasks
    phone_number: str
    gsm7: bool


async def _start_check(
    sending: _Sending, check_id: str, text: str, hashed: str
) -> Received:
    try:
        payload = await _check_input(text, hashed, sending.pii)
    except ValidationError:
        if len(text) > TEXT_MAX_CHARS:
            too_long = one_sms(TOO_LONG_TEXT, gsm7=sending.gsm7)
            sending.background.add_task(
                sending.sms.send, sending.phone_number, too_long
            )
        return Received(status="rejected")
    # the hash stands for the address: one sender's own budget, not the relay's
    origin = Origin(ip=hashed, region=SMS_REGION)
    if await sending.gate.refusal(origin, CHANNEL) is not None:
        return Received(status="refused")
    first = not await sending.records.list_for(CHANNEL_USER, hashed)
    await sending.jobs.enqueue(CHECK, payload, workflow_id=check_id)
    sending.background.add_task(
        reply_when_done,
        sending.jobs,
        sending.sms,
        check_id,
        sending.phone_number,
        first_contact=first,
        gsm7=sending.gsm7,
    )
    return Received(status="accepted")
