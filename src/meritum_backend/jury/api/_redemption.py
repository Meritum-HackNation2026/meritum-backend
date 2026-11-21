"""Redeem a jury link after checking the client address budget."""

import hmac
import re
import secrets
import time
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, SecretStr, ValidationError

from meritum_backend.auth import Account
from meritum_backend.auth.constants import (
    SESSION_ACCOUNT,
    SESSION_CSRF,
    SESSION_EXPIRES,
    SESSION_READ_ONLY,
    SESSION_SINCE,
    TOKEN_BYTES,
)
from meritum_backend.constants import MINUTE_SECONDS
from meritum_backend.jury.constants import (
    EVALUATION_PAGE,
    JSON_MEDIA_TYPE,
    JURY_LINK_ATTEMPTS,
    JURY_PROVIDER,
    JURY_RATE_SCOPE,
    LINK_PATTERN,
    MAX_REDEMPTION_BYTES,
    NO_STORE,
)
from meritum_backend.jury.ports import JuryLinks, JuryUnavailableError
from meritum_backend.limits import ClientOrigin
from meritum_backend.limits.ports import RateCounter

router = APIRouter()


class JuryRedemption(BaseModel):
    """Redeem a link by sending its token in the request body.

    Attributes:
        token: the token extracted from the URL fragment.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    token: SecretStr


def get_jury_links(request: Request) -> JuryLinks:
    """Return the configured link store.

    Args:
        request: request whose app owns the store.

    Returns:
        The app's link store.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    return request.app.state.jury_links


Store = Annotated[JuryLinks, Depends(get_jury_links)]


async def _admit(request: Request, ip: str) -> None:
    counter = cast("RateCounter", request.app.state.jury_rate_counter)
    secret = cast("bytes", request.app.state.jury_rate_secret)
    digest = hmac.new(secret, f"{JURY_RATE_SCOPE}:{ip}".encode(), sha256).hexdigest()
    hits = await counter.hit(f"{JURY_RATE_SCOPE}:{digest}", MINUTE_SECONDS)
    if hits == 0:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, headers=NO_STORE)
    if hits > JURY_LINK_ATTEMPTS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many jury link attempts",
            {**NO_STORE, "Retry-After": str(MINUTE_SECONDS)},
        )


async def _read_token(request: Request) -> str:
    # a text/plain cross-site form could otherwise log a victim into a jury session
    media_type = request.headers.get("content-type", "").split(";")[0].strip()
    if media_type.lower() != JSON_MEDIA_TYPE:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, headers=NO_STORE)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REDEMPTION_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, headers=NO_STORE)
        body.extend(chunk)
    try:
        return JuryRedemption.model_validate_json(body).token.get_secret_value()
    except ValidationError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid redemption body", NO_STORE
        ) from None


@router.post(
    "/auth/jury-links/redeem",
    status_code=status.HTTP_303_SEE_OTHER,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": JuryRedemption.model_json_schema()}
            },
        }
    },
)
async def redeem_jury_link(
    request: Request, origin: ClientOrigin, store: Store
) -> RedirectResponse:
    """Exchange the token for a read-only analyst cookie and redirect to evaluation.

    Args:
        request: the request with the signed session.
        origin: the client address used for rate limiting.
        store: link store.

    Returns:
        A redirect to the evaluation page.

    Raises:
        HTTPException: invalid, expired, or rate-limited request, or storage error.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    await _admit(request, origin.ip)
    token = await _read_token(request)
    if not re.fullmatch(LINK_PATTERN, token):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invalid jury link", NO_STORE)
    now = datetime.now(UTC)
    try:
        expires_at = await store.consume(sha256(token.encode()).digest(), now)
    except JuryUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    if expires_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invalid jury link", NO_STORE)
    if expires_at <= now:
        raise HTTPException(status.HTTP_410_GONE, "jury link expired", NO_STORE)
    request.session.clear()
    request.session.update(
        {
            SESSION_ACCOUNT: Account(
                provider=JURY_PROVIDER, subject=secrets.token_urlsafe(TOKEN_BYTES)
            ).model_dump(),
            SESSION_CSRF: secrets.token_urlsafe(TOKEN_BYTES),
            SESSION_SINCE: int(time.time()),
            SESSION_EXPIRES: expires_at.timestamp(),
            SESSION_READ_ONLY: True,
        }
    )
    return RedirectResponse(EVALUATION_PAGE, status.HTTP_303_SEE_OTHER, NO_STORE)
