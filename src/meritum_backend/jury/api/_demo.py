"""Reusable demo links for the technical accounts (dev environment only)."""

import re
import secrets
import time
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import AwareDatetime, BaseModel, SecretStr

from meritum_backend.auth import Account
from meritum_backend.auth.api import CsrfUser
from meritum_backend.auth.constants import (
    LOCAL_URL,
    PUBLIC_URLS,
    SESSION_ACCOUNT,
    SESSION_CSRF,
    SESSION_EXPIRES,
    SESSION_SINCE,
    TOKEN_BYTES,
)
from meritum_backend.jury.api._redemption import Store, admit
from meritum_backend.jury.constants import (
    DEMO_ACCOUNTS,
    DEMO_ENVS,
    DEMO_PATH,
    DEMO_PROVIDER,
    JURY_LINK_MAX_TTL,
    JURY_LINK_TTL,
    LINK_PATTERN,
    NO_STORE,
)
from meritum_backend.jury.ports import JuryUnavailableError
from meritum_backend.limits import ClientOrigin
from meritum_backend.settings import Settings, get_settings
from meritum_backend.staff.api import RealAdmin

router = APIRouter()

type DemoAccount = Literal["obywatel", "admin"]


def demo_hash(account: str, token: str) -> bytes:
    """Digest that stores a demo token for one account (never equals a jury digest).

    Args:
        account: the technical account the link opens.
        token: the raw link token.

    Returns:
        The SHA-256 digest of the account-scoped token.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    return sha256(f"demo:{account}:{token}".encode()).digest()


def _require_demo_env(settings: Settings) -> None:
    if settings.env not in DEMO_ENVS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, headers=NO_STORE)


class DemoLinkRequest(BaseModel):
    """Which technical account the new link opens.

    Attributes:
        account: ``obywatel`` or ``admin``.
        expires_at: deadline, at most 7 days ahead; 24 hours when absent.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    account: DemoAccount
    expires_at: AwareDatetime | None = None


class DemoLinkRevocation(BaseModel):
    """The link to revoke, identified by its token.

    Attributes:
        account: the account the link opens.
        token: the raw token (the last segment of the link).

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    account: DemoAccount
    token: SecretStr


class IssuedDemoLink(BaseModel):
    """The administrator's only copy of the link.

    Attributes:
        url: backend address that signs the visitor in.
        expires_at: last moment the link works.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    url: str
    expires_at: datetime


@router.post("/staff/demo-links", status_code=status.HTTP_201_CREATED)
async def issue_demo_link(
    body: DemoLinkRequest,
    response: Response,
    _admin: RealAdmin,
    _csrf: CsrfUser,
    store: Store,
    settings: Annotated[Settings, Depends(get_settings)],
) -> IssuedDemoLink:
    """Issue a reusable link into a technical account.

    Args:
        body: the account and optional deadline.
        response: outgoing response with caching disabled.
        _admin: the signed-in administrator (not a demo session).
        _csrf: the account, CSRF checked.
        store: link store.
        settings: environment and public address.

    Returns:
        The URL (shown once) and its deadline.

    Raises:
        HTTPException: 404 outside dev, 422 for a bad deadline, 503 on storage failure.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    _require_demo_env(settings)
    now = datetime.now(UTC)
    deadline = body.expires_at or now + JURY_LINK_TTL
    if not now < deadline <= now + JURY_LINK_MAX_TTL:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid deadline")
    token = secrets.token_urlsafe(TOKEN_BYTES)
    try:
        await store.save(demo_hash(body.account, token), deadline)
    except JuryUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    origin = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    response.headers.update(NO_STORE)
    return IssuedDemoLink(
        url=f"{origin.rstrip('/')}{DEMO_PATH}{token}", expires_at=deadline
    )


@router.post("/staff/demo-links/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_demo_link(
    body: DemoLinkRevocation, _admin: RealAdmin, _csrf: CsrfUser, store: Store
) -> None:
    """Revoke a demo link so it stops working at once.

    Args:
        body: the account and token of the link.
        _admin: the signed-in administrator (not a demo session).
        _csrf: the account, CSRF checked.
        store: link store.

    Raises:
        HTTPException: 404 when no such link exists, 503 on storage failure.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    digest = demo_hash(body.account, body.token.get_secret_value())
    try:
        removed = await store.remove(digest)
    except JuryUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such demo link")


@router.get("/auth/demo/{token}", status_code=status.HTTP_303_SEE_OTHER)
async def open_demo_link(
    token: str,
    request: Request,
    origin: ClientOrigin,
    store: Store,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Sign the visitor in as the technical account the link was issued for.

    Args:
        token: the raw token from the link.
        request: the request holding the session.
        origin: the client address used for rate limiting.
        store: link store.
        settings: environment.

    Returns:
        A redirect to the account's landing page, without the token.

    Raises:
        HTTPException: 404 outside dev or for an unknown or malformed link,
            410 when expired, 429 when rate limited, 503 on storage failure.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    _require_demo_env(settings)
    await admit(request, origin.ip)
    now = datetime.now(UTC)
    found: tuple[str, datetime] | None = None
    if re.fullmatch(LINK_PATTERN, token):
        for account in DEMO_ACCOUNTS:
            try:
                expires_at = await store.peek(demo_hash(account, token), now)
            except JuryUnavailableError:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
            if expires_at is not None:
                found = (account, expires_at)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "demo link does not work", NO_STORE
        )
    account, expires_at = found
    request.session.clear()
    request.session.update(
        {
            SESSION_ACCOUNT: Account(
                provider=DEMO_PROVIDER, subject=account
            ).model_dump(),
            SESSION_CSRF: secrets.token_urlsafe(TOKEN_BYTES),
            SESSION_SINCE: int(time.time()),
            SESSION_EXPIRES: expires_at.timestamp(),
        }
    )
    return RedirectResponse(DEMO_ACCOUNTS[account], status.HTTP_303_SEE_OTHER, NO_STORE)
