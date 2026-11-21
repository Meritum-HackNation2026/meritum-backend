"""Staff issuance of jury links and the read-only guard for jury sessions."""

import secrets
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AwareDatetime, BaseModel

from meritum_backend.auth.api import CsrfUser
from meritum_backend.auth.constants import (
    LOCAL_URL,
    LOGOUT_PATH,
    PUBLIC_URLS,
    SESSION_READ_ONLY,
    TOKEN_BYTES,
)
from meritum_backend.jury.api._redemption import Store
from meritum_backend.jury.api._redemption import router as redemption_router
from meritum_backend.jury.constants import (
    JURY_LANDING,
    JURY_LINK_MAX_TTL,
    JURY_LINK_TTL,
    NO_STORE,
    SAFE_METHODS,
)
from meritum_backend.jury.ports import JuryUnavailableError
from meritum_backend.staff.api import Admin

router = APIRouter(prefix="/api/v1", tags=["jury"])
router.include_router(redemption_router)


class IssuedJuryLink(BaseModel):
    """The administrator's sole copy of the shareable link.

    Attributes:
        url: public jury page with the raw token in the URL fragment.
        expires_at: last moment before the link expires.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    url: str
    expires_at: datetime


def require_writable_session(request: Request) -> None:
    """Disallow state-changing API requests from a jury session.

    Args:
        request: current request with the signed session.

    Raises:
        HTTPException: 403 for an unsafe method from a jury session.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    if (
        request.method not in SAFE_METHODS
        and request.url.path != LOGOUT_PATH
        and request.session.get(SESSION_READ_ONLY)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "read-only session")


@router.post("/staff/jury-links", status_code=status.HTTP_201_CREATED)
async def issue_jury_link(
    request: Request,
    response: Response,
    _admin: Admin,
    _csrf: CsrfUser,
    store: Store,
    expires_at: AwareDatetime | None = None,
) -> IssuedJuryLink:
    """Issue a short-lived link that can be redeemed only once.

    Args:
        request: the request whose app holds the public URL.
        response: outgoing response with caching disabled.
        store: link store.
        expires_at: end of the evaluation, at most 7 days ahead; 24 hours if absent.

    Returns:
        The URL and its deadline.

    Raises:
        HTTPException: 422 for an invalid deadline or 503 when storage fails.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    now = datetime.now(UTC)
    deadline = expires_at or now + JURY_LINK_TTL
    if not now < deadline <= now + JURY_LINK_MAX_TTL:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid jury link deadline"
        )
    token = secrets.token_urlsafe(TOKEN_BYTES)
    try:
        await store.save(sha256(token.encode()).digest(), deadline)
    except JuryUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    settings = request.app.state.settings
    origin = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    response.headers.update(NO_STORE)
    return IssuedJuryLink(
        url=f"{origin.rstrip('/')}{JURY_LANDING}#{token}", expires_at=deadline
    )
