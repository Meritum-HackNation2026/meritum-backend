"""Reusable demo links for the technical accounts (dev environment only)."""

import re
import secrets
import time
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, SecretStr

from meritum_backend.auth import Account
from meritum_backend.auth.constants import (
    SESSION_ACCOUNT,
    SESSION_CSRF,
    SESSION_EXPIRES,
    SESSION_SINCE,
    TOKEN_BYTES,
)
from meritum_backend.jury.api._redemption import Store, admit
from meritum_backend.jury.constants import (
    DEMO_ACCOUNTS,
    DEMO_ADMIN,
    DEMO_ENVS,
    DEMO_PROVIDER,
    LINK_PATTERN,
    NO_STORE,
)
from meritum_backend.jury.ports import JuryUnavailableError
from meritum_backend.limits import ClientOrigin
from meritum_backend.settings import Settings, get_settings

router = APIRouter()


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


def require_demo_env(settings: Settings) -> None:
    """Restrict demo links to development environments.

    Args:
        settings: active environment settings.

    Raises:
        HTTPException: demo links do not exist in this environment.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    if settings.env not in DEMO_ENVS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, headers=NO_STORE)


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
    require_demo_env(settings)
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


class PasswordLogin(BaseModel):
    """Login and password the jury got in the submission.

    Attributes:
        login: the configured jury login.
        password: the configured jury password.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    login: str
    password: SecretStr


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
async def password_login(
    body: PasswordLogin,
    request: Request,
    origin: ClientOrigin,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Sign the jury in as the demo administrator with a login and password.

    Args:
        body: the login and password.
        request: the request holding the session.
        origin: the client address used for rate limiting.
        settings: the configured jury login and password.

    Raises:
        HTTPException: 404 when no jury password is configured, 401 on a wrong
            login or password, 429 when rate limited.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    if settings.jury_login is None or settings.jury_password is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, headers=NO_STORE)
    await admit(request, origin.ip)
    login_ok = secrets.compare_digest(body.login.encode(), settings.jury_login.encode())
    password_ok = secrets.compare_digest(
        body.password.get_secret_value().encode(),
        settings.jury_password.get_secret_value().encode(),
    )
    if not (login_ok and password_ok):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "wrong login or password", NO_STORE
        )
    request.session.clear()
    request.session.update(
        {
            SESSION_ACCOUNT: Account(
                provider=DEMO_PROVIDER, subject=DEMO_ADMIN
            ).model_dump(),
            SESSION_CSRF: secrets.token_urlsafe(TOKEN_BYTES),
            SESSION_SINCE: int(time.time()),
        }
    )
