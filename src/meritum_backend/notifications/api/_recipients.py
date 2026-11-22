"""Who is asking: the browser session and the signed-in account of a request.

Features:
    US-POW-01, US-POW-04, F-26
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status
from meritum_core.notifications import RecipientKind

from meritum_backend.auth import Account
from meritum_backend.auth.api import current_user
from meritum_backend.checks import SESSION_HEADER
from meritum_backend.notifications.announcer import staff_inbox_id
from meritum_backend.notifications.constants import (
    NO_RECIPIENT_DETAIL,
    SESSION_ID_MAX,
    SESSION_ID_MIN,
    SESSION_QUERY,
)

type Recipient = tuple[RecipientKind, str]
"""One inbox the caller may read: a session id or an account's user id."""


def signed_in_account(request: Request) -> Account | None:
    """The signed-in account, or None for an anonymous caller.

    Args:
        request: the current request.

    Returns:
        The account from the session cookie, if any.

    Features:
        US-POW-04, F-26
    """
    try:
        return current_user(request)
    except HTTPException:
        return None


def recipients(
    account: Annotated[Account | None, Depends(signed_in_account)],
    header: Annotated[
        str | None,
        Header(
            alias=SESSION_HEADER, min_length=SESSION_ID_MIN, max_length=SESSION_ID_MAX
        ),
    ] = None,
    query: Annotated[
        str | None,
        Query(
            alias=SESSION_QUERY, min_length=SESSION_ID_MIN, max_length=SESSION_ID_MAX
        ),
    ] = None,
) -> list[Recipient]:
    """Every inbox the caller may read: its session and its account.

    The session comes from the header, or from the query for EventSource,
    which cannot send headers; the access log masks the query (privacy).

    Args:
        account: the signed-in account, if any.
        header: the session id from the X-Meritum-Session header.
        query: the session id from ``?session=``.

    Returns:
        One or two recipients.

    Raises:
        HTTPException: 400 with neither a session nor an account.

    Features:
        US-POW-01, US-POW-04, F-26
    """
    found: list[Recipient] = []
    session = header or query
    if session is not None:
        found.append(("session_id", session))
    if account is not None:
        found.append(("user_id", f"{account.provider}:{account.subject}"))
        if account.email is not None and account.email_verified:
            found.append(("user_id", staff_inbox_id(account.email)))
    if not found:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, NO_RECIPIENT_DETAIL)
    return found
