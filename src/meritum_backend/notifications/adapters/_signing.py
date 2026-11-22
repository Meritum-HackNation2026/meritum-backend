"""Signed POST shared by the webhook and the e-mail Worker adapters.

Features:
    US-POW-05, US-MOD-01, F-26
"""

import hashlib
import hmac
import json
import time
from collections.abc import Mapping

import httpx2

from meritum_backend.notifications.constants import (
    HTTP_TIMEOUT_SECONDS,
    SIGNATURE_HEADER,
    SIGNATURE_PREFIX,
    TIMESTAMP_HEADER,
)
from meritum_backend.notifications.ports import NotifyError


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """The HMAC-SHA256 header value of ``"<timestamp>.<body>"``.

    Args:
        secret: the shared secret.
        timestamp: Unix seconds, as sent in the timestamp header.
        body: the raw request body.

    Returns:
        ``sha256=<hex>``.

    Features:
        US-POW-05, US-MOD-01, F-26
    """
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return SIGNATURE_PREFIX + mac.hexdigest()


async def post_signed(
    url: str,
    payload: Mapping[str, object],
    secret: str,
    transport: httpx2.AsyncBaseTransport | None,
) -> None:
    """POST ``payload`` as JSON with a fresh timestamp and signature.

    Args:
        url: the target.
        payload: the JSON body.
        secret: signs the body.
        transport: a mock transport in tests; the network when None.

    Features:
        US-POW-05, US-MOD-01, F-26
    """
    body = json.dumps(payload, separators=(",", ":")).encode()
    stamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: stamp,
        SIGNATURE_HEADER: sign(secret, stamp, body),
    }
    await post(url, body, headers, transport)


async def post(
    url: str,
    body: bytes,
    headers: dict[str, str],
    transport: httpx2.AsyncBaseTransport | None,
) -> None:
    """POST a body, turning any failure into NotifyError.

    Args:
        url: the target.
        body: the raw body.
        headers: the request headers.
        transport: a mock transport in tests; the network when None.

    Raises:
        NotifyError: an error status or no answer.

    Features:
        US-POW-05, US-MOD-01, F-26
    """
    try:
        async with httpx2.AsyncClient(
            transport=transport, timeout=HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, content=body, headers=headers)
        response.raise_for_status()
    except httpx2.HTTPError as exc:
        # only the type: the message may carry the target's secret address
        raise NotifyError(type(exc).__name__) from exc
