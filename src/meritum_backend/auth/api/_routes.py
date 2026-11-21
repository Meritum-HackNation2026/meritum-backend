"""Auth routes: OIDC login, callback, the current account and logout."""

import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from meritum_backend.auth import LoginError, PendingLogin
from meritum_backend.auth.api._session import (
    CurrentUser,
    Login,
    check_csrf,
    same_secret,
)
from meritum_backend.auth.constants import (
    CALLBACK_PATH,
    HOME,
    LOCAL_URL,
    PUBLIC_URLS,
    RETURN_TO_DOC,
    SESSION_ACCOUNT,
    SESSION_CSRF,
    SESSION_PENDING,
    SESSION_SINCE,
    TOKEN_BYTES,
)
from meritum_backend.auth.models import Me
from meritum_backend.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _callback_url(settings: Settings, provider: str) -> str:
    base = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    return base.rstrip("/") + CALLBACK_PATH.format(provider=provider)


@router.get("/login/{provider}")
async def login(
    provider: str,
    request: Request,
    login: Login,
    settings: Annotated[Settings, Depends(get_settings)],
    return_to: Annotated[str, Query(description=RETURN_TO_DOC)] = HOME,
) -> RedirectResponse:
    """Send the user to the provider's login page.

    Args:
        provider: ``google`` or ``microsoft``.
        request: the request; its session keeps the login in progress.
        login: the login provider port.
        settings: the app settings (public address for the callback).
        return_to: the page to open after login; kept with the login in
            progress, anything but a relative path on this site means ``HOME``.

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
    # validated: an unsafe return_to becomes HOME (no open redirect)
    pending = start.pending.model_dump() | {"return_to": return_to}
    request.session[SESSION_PENDING] = PendingLogin.model_validate(pending).model_dump()
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
    return pending if same_secret(pending.state, state) else None


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
        A redirect to the page the login started from (``return_to``, else
        the web app's home page), with a new session.

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
    return RedirectResponse(pending.return_to, status.HTTP_303_SEE_OTHER)


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
async def logout(request: Request, _account: CurrentUser) -> None:
    """End the session: the cookie is replaced by an expired one.

    A read-only (jury) session may log out too, so this skips ``CsrfUser``.

    Args:
        request: the request whose session is cleared.
        _account: the signed-in account (CSRF checked here, 403 on mismatch).

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    check_csrf(request)
    request.session.clear()
