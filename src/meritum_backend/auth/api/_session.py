"""Session dependencies: the login provider, the signed-in account and CSRF.

The session is Starlette's signed cookie (main.py: httpOnly, Secure,
SameSite=Lax). State-changing requests made with it repeat the session's CSRF
token in the ``X-CSRF-Token`` header (``CsrfUser``).
"""

import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from pydantic import ValidationError

from meritum_backend.auth import Account, LoginProvider
from meritum_backend.auth.constants import (
    CSRF_HEADER,
    SESSION_ACCOUNT,
    SESSION_CSRF,
    SESSION_EXPIRES,
    SESSION_MAX_AGE,
    SESSION_READ_ONLY,
    SESSION_SINCE,
)


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


def optional_user(request: Request) -> Account | None:
    """The signed-in account, or None for an anonymous visitor.

    Signing in is optional for citizens: a check works without it.

    Args:
        request: the current request.

    Returns:
        The account from a valid session, else None.

    Features:
        US-SPR-10, F-31
    """
    try:
        return current_user(request)
    except HTTPException:
        return None


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
        HTTPException: 403 on a CSRF mismatch or for a read-only (jury) session.

    Features:
        US-MOD-05, US-SPR-10, US-OBS-06, F-25, F-28
    """
    check_csrf(request)
    if request.session.get(SESSION_READ_ONLY):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "read-only session")
    return account


def check_csrf(request: Request) -> None:
    """Require the session's CSRF token in the ``X-CSRF-Token`` header.

    Args:
        request: the current request.

    Raises:
        HTTPException: 403 when the token is missing or differs.

    Features:
        US-MOD-05, F-25
    """
    expected = str(request.session.get(SESSION_CSRF, ""))
    if not expected or not same_secret(expected, request.headers.get(CSRF_HEADER, "")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or bad CSRF token")


def same_secret(expected: str, sent: str) -> bool:
    """Compare two secrets in constant time.

    Bytes, so non-ASCII input is a mismatch, not a 500.

    Args:
        expected: the value the session holds.
        sent: the value the client sent.

    Returns:
        Whether they are equal.

    Features:
        US-MOD-05, F-25
    """
    return secrets.compare_digest(expected.encode(), sent.encode())


Login = Annotated[LoginProvider, Depends(get_login)]
CurrentUser = Annotated[Account, Depends(current_user)]
OptionalUser = Annotated[Account | None, Depends(optional_user)]
CsrfUser = Annotated[Account, Depends(csrf_user)]
