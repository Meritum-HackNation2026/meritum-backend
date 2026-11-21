"""POST /api/v1/discord/interactions: Discord HTTP interactions (inbound adapter).

Discord signs every request with the app's Ed25519 key; unsigned or badly signed
requests get 401 (Discord itself probes this and drops endpoints that accept them).
Without MERITUM_DISCORD_PUBLIC_KEY the endpoint does not exist (404).

Features:
    US-WTY-06, US-BEZ-07, F-03, F-21, ADR-08
"""

import json
from typing import Annotated, Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from meritum_backend.auth.constants import LOCAL_URL, PUBLIC_URLS
from meritum_backend.checks.api import Cache, PiiGate, Records
from meritum_backend.discord.api._delivery import Interaction, reply_when_done
from meritum_backend.discord.api._intake import Ports, start, user_hash
from meritum_backend.discord.constants import (
    APPLICATION_COMMAND,
    CARD_PATH,
    CHANNEL_USER,
    CHECK,
    CHECK_MESSAGE,
    DEFERRED_CHANNEL_MESSAGE,
    EPHEMERAL,
    PING,
    PONG,
    TEXT_OPTION,
)
from meritum_backend.discord.ports import InteractionReplies
from meritum_backend.health.api import Ready
from meritum_backend.jobs.api import Jobs
from meritum_backend.limits import Gate
from meritum_backend.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/discord", tags=["discord"])


def signature_is_valid(
    public_key: str, signature: str, timestamp: str, body: bytes
) -> bool:
    """Check Discord's Ed25519 signature over timestamp + raw body.

    Args:
        public_key: the app's public key, hex.
        signature: the X-Signature-Ed25519 header, hex.
        timestamp: the X-Signature-Timestamp header.
        body: the raw request body.

    Returns:
        True only for a well-formed, valid signature.

    Features:
        US-WTY-06
    """
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
        key.verify(bytes.fromhex(signature), timestamp.encode() + body)
    except InvalidSignature, ValueError:
        return False
    return True


def command_text(data: dict[str, Any]) -> str:
    """Text the user asked about: the slash command option or the target message.

    Args:
        data: the interaction's ``data`` object.

    Returns:
        The text, empty when there is none.

    Features:
        US-WTY-06
    """
    if data.get("name") == CHECK:
        options = data.get("options") or []
        return next(
            (str(o.get("value", "")) for o in options if o.get("name") == TEXT_OPTION),
            "",
        )
    if data.get("name") == CHECK_MESSAGE:
        messages = (data.get("resolved") or {}).get("messages") or {}
        return str((messages.get(data.get("target_id")) or {}).get("content", ""))
    return ""


def get_replies(request: Request) -> InteractionReplies:
    """The Discord sender the app built at startup (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The interaction replies sender.

    Features:
        US-WTY-06, F-03
    """
    return request.app.state.discord_replies


Replies = Annotated[InteractionReplies, Depends(get_replies)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _user_id(interaction: dict[str, Any]) -> str:
    # in a server the user sits under ``member``; in DMs at the top level
    user = (interaction.get("member") or {}).get("user") or interaction.get("user")
    return str((user or {}).get("id", ""))


def _card_url(settings: Settings, check_id: str) -> str:
    base = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    return base.rstrip("/") + CARD_PATH.format(check_id=check_id)


@router.post("/interactions")
async def interactions(  # ruff: ignore[too-many-arguments, too-many-positional-arguments] (FastAPI injects each port as a parameter)
    request: Request,
    settings: AppSettings,
    jobs: Jobs,
    gate: Gate,
    pii: PiiGate,
    readiness: Ready,
    cache: Cache,
    records: Records,
    replies: Replies,
    background: BackgroundTasks,
) -> dict[str, Any]:
    """Answer a Discord interaction; a command starts the same check as the web form.

    The answer is deferred at once (Discord waits 3 s); the result follows as an
    edit of that answer plus one message per claim.

    Args:
        request: the signed HTTP interaction.
        settings: the Discord public key, the hash salt, the card's address.
        jobs: the job queue port.
        gate: the shared rate limits and the pending-checks threshold.
        pii: masks personal data in the text before it is queued.
        readiness: a service that is not ready refuses checks.
        cache: the result cache.
        records: check records; none for the user hash means first contact.
        replies: the Discord sender of the result.
        background: runs the reply after the answer.

    Returns:
        PONG for Discord's PING, a deferred answer for a started check, else an
        ephemeral message saying why the check did not start.

    Raises:
        HTTPException: 404 when Discord is not configured, 401 for a bad signature,
            400 for an interaction type Meritum does not handle.

    Features:
        US-WTY-06, US-BEZ-07, F-03, F-21, ADR-08
    """
    public_key = settings.discord_public_key
    if public_key is None or not public_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    body = await request.body()
    if not signature_is_valid(
        public_key,
        request.headers.get("X-Signature-Ed25519", ""),
        request.headers.get("X-Signature-Timestamp", ""),
        body,
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid request signature")
    interaction = json.loads(body)
    if not isinstance(interaction, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported interaction")
    if interaction.get("type") == PING:
        return {"type": PONG}
    if interaction.get("type") != APPLICATION_COMMAND:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported interaction")
    user_id = _user_id(interaction)
    hashed = user_hash(settings, user_id)
    first = hashed is None or not await records.list_for(CHANNEL_USER, hashed)
    ports = Ports(jobs, gate, pii, readiness, cache, records, settings)
    started = await start(ports, command_text(interaction.get("data") or {}), user_id)
    if not isinstance(started, str):
        return started
    target = Interaction(
        application_id=str(interaction.get("application_id", "")),
        token=str(interaction.get("token", "")),
        card_url=_card_url(settings, started),
        first_contact=first,
    )
    background.add_task(reply_when_done, jobs, cache, replies, started, target)
    return {"type": DEFERRED_CHANNEL_MESSAGE, "data": {"flags": EPHEMERAL}}
