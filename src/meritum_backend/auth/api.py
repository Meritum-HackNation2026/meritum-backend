"""Auth API: OIDC login, callback, the current account and logout.

The session is Starlette's signed cookie (main.py: httpOnly, Secure,
SameSite=Lax). State-changing requests made with it repeat the session's CSRF
token in the ``X-CSRF-Token`` header (``CsrfUser``).
"""

import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from meritum_backend.auth import Account, LoginError, LoginProvider, PendingLogin
from meritum_backend.auth.constants import (
    CALLBACK_PATH,
    CSRF_HEADER,
    HOME,
    LOCAL_URL,
    PUBLIC_URLS,
    SESSION_ACCOUNT,
    SESSION_CSRF,
    SESSION_EXPIRES,
    SESSION_MAX_AGE,
    SESSION_PENDING,
    SESSION_SINCE,
    TOKEN_BYTES,
)
from meritum_backend.auth.models import Me
from meritum_backend.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_login(request: Request) -> LoginProvider:
    """The login provider the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's login provider.

    Features:
        US-MOD-05, F-25
    """
    return request.app.state.login


def current_user(request: Request) -> Account:
    """The signed-in account from the session cookie.

    Args:
        request: the current request.

    Returns:
        The account.

    Raises:
        HTTPException: 401 without a valid session.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    since = request.session.get(SESSION_SINCE)
    fresh = isinstance(since, int) and time.time() - since < SESSION_MAX_AGE
    try:
        account = Account.model_validate(request.session.get(SESSION_ACCOUNT))
    except ValidationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in") from exc
    expiry = request.session.get(SESSION_EXPIRES)
    if not fresh or (isinstance(expiry, (int, float)) and expiry <= time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    return account


def csrf_user(
    request: Request, account: Annotated[Account, Depends(current_user)]
) -> Account:
    """The signed-in account, for a state-changing request with a CSRF token.

    Args:
        request: the current request.
        account: the signed-in account.

    Returns:
        The account.

    Raises:
        HTTPException: 403 when the header does not match the session's token.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    expected = str(request.session.get(SESSION_CSRF, ""))
    sent = request.headers.get(CSRF_HEADER, "")
    if not expected or not _same(expected, sent):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or bad CSRF token")
    return account


def _same(expected: str, sent: str) -> bool:
    """Compare in constant time; bytes, so non-ASCII input is a mismatch, not a 500.

    Args:
        expected: the value kept in the session.
        sent: the value from the request.

    Returns:
        Whether both are equal.
    """
    return secrets.compare_digest(expected.encode(), sent.encode())


Login = Annotated[LoginProvider, Depends(get_login)]
CurrentUser = Annotated[Account, Depends(current_user)]
CsrfUser = Annotated[Account, Depends(csrf_user)]


def _callback_url(settings: Settings, provider: str) -> str:
    base = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    return base.rstrip("/") + CALLBACK_PATH.format(provider=provider)


@router.get("/login/{provider}")
async def login(
    provider: str,
    request: Request,
    login: Login,
    settings: Annotated[Settings, Depends(get_settings)],
) -> RedirectResponse:
    """Send the user to the provider's login page.

    Args:
        provider: ``google`` or ``microsoft``.
        request: the request; its session keeps the login in progress.
        login: the login provider port.
        settings: the app settings (public address for the callback).

    Returns:
        A redirect to the provider.

    Raises:
        HTTPException: 404 for a provider that is not configured, 502 when the
            provider's discovery document cannot be read.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    if provider not in login.providers:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown login provider")
    try:
        start = await login.begin(provider, _callback_url(settings, provider))
    except LoginError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "provider unavailable"
        ) from exc
    request.session[SESSION_PENDING] = start.pending.model_dump()
    return RedirectResponse(start.url, status.HTTP_302_FOUND)


def _pending(request: Request, state: str) -> PendingLogin | None:
    """Take the login in progress out of the session.

    Args:
        request: the request with the session.
        state: the state the provider sent back.

    Returns:
        The pending login when ``state`` matches it, else None (single use).
    """
    try:
        pending = PendingLogin.model_validate(
            request.session.pop(SESSION_PENDING, None)
        )
    except ValidationError:
        return None
    return pending if _same(pending.state, state) else None


@router.get("/callback/{provider}")
async def callback(
    provider: str, request: Request, login: Login, code: str = "", state: str = ""
) -> RedirectResponse:
    """Finish the login and start a session.

    Args:
        provider: the provider name from the path.
        request: the request with the session cookie.
        login: the login provider port.
        code: the authorization code from the provider.
        state: the state the provider sends back unchanged.

    Returns:
        A redirect to the web app's home page, with a new session.

    Raises:
        HTTPException: 400 when the state does not match the session, or the
            provider does not confirm the account; no session is created.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    pending = _pending(request, state)
    if pending is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid login state")
    try:
        account = await login.complete(provider, code, pending)
    except LoginError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "login refused") from exc
    request.session.clear()
    request.session[SESSION_ACCOUNT] = account.model_dump()
    request.session[SESSION_CSRF] = secrets.token_urlsafe(TOKEN_BYTES)
    request.session[SESSION_SINCE] = int(time.time())
    return RedirectResponse(HOME, status.HTTP_303_SEE_OTHER)


@router.get("/me")
async def me(request: Request, account: CurrentUser) -> Me:
    """The signed-in account.

    Args:
        request: the request (the session's CSRF token).
        account: the signed-in account.

    Returns:
        The account id, e-mail address and CSRF token.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    csrf_token = str(request.session.get(SESSION_CSRF, ""))
    return Me(**account.model_dump(), csrf_token=csrf_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, _account: CsrfUser) -> None:
    """End the session: the cookie is replaced by an expired one.

    Args:
        request: the request whose session is cleared.
        _account: the signed-in account (CSRF checked).

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    request.session.clear()
