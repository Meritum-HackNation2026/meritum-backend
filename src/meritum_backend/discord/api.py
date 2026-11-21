"""POST /api/v1/discord/interactions: Discord HTTP interactions (inbound adapter).

Discord signs every request with the app's Ed25519 key; unsigned or badly signed
requests get 401 (Discord itself probes this and drops endpoints that accept them).
Without MERITUM_DISCORD_PUBLIC_KEY the endpoint does not exist (404).
"""

import json
from typing import Annotated, Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request, status
from meritum_core.checks.contracts import CheckRequest
from pydantic import ValidationError

from meritum_backend.discord.constants import (
    APPLICATION_COMMAND,
    CHANNEL_MESSAGE,
    CHECK,
    CHECK_MESSAGE,
    EPHEMERAL,
    PING,
    PONG,
    TEXT_OPTION,
)
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


def answer(text: str) -> str:
    """Reply to a check request (bootstrap: the verification core does not exist yet).

    Args:
        text: the text the user asked about.

    Returns:
        The message shown to the user.

    Features:
        US-WTY-06, US-SPR-06
    """
    try:
        CheckRequest.model_validate({"channel": "discord", "text": text})
    except ValidationError:
        return "Wyślij tekst do sprawdzenia (co najmniej 3 znaki) albo link."
    return (
        "Przyjąłem tekst do sprawdzenia. Meritum jest w budowie: werdykt ze "
        "źródłami pojawi się tutaj, gdy rdzeń weryfikacji będzie gotowy."
    )


@router.post("/interactions")
async def interactions(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    """Answer a Discord interaction.

    Args:
        request: the signed HTTP interaction.
        settings: the app settings (the Discord public key).

    Returns:
        PONG for Discord's PING, else an ephemeral message.

    Raises:
        HTTPException: 404 when Discord is not configured, 401 for a bad signature,
            400 for an interaction type Meritum does not handle.

    Features:
        US-WTY-06, ADR-08
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
    if interaction.get("type") == PING:
        return {"type": PONG}
    if interaction.get("type") == APPLICATION_COMMAND:
        text = command_text(interaction.get("data") or {})
        return {
            "type": CHANNEL_MESSAGE,
            "data": {"content": answer(text), "flags": EPHEMERAL},
        }
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported interaction")
