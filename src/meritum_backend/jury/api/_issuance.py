"""Staff issuance of jury links."""

import secrets
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AwareDatetime, BaseModel

from meritum_backend.auth.api import CsrfUser
from meritum_backend.auth.constants import (
    LOCAL_URL,
    PUBLIC_URLS,
    TOKEN_BYTES,
)
from meritum_backend.jury.api._demo import router as demo_router
from meritum_backend.jury.api._redemption import Store
from meritum_backend.jury.api._redemption import router as redemption_router
from meritum_backend.jury.constants import (
    JURY_LANDING,
    JURY_LINK_MAX_TTL,
    JURY_LINK_TTL,
    NO_STORE,
)
from meritum_backend.jury.ports import JuryUnavailableError
from meritum_backend.settings import Settings, get_settings
from meritum_backend.staff.api import RealAdmin

router = APIRouter(prefix="/api/v1", tags=["jury"])
router.include_router(redemption_router)
router.include_router(demo_router)


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


@router.post("/staff/jury-links", status_code=status.HTTP_201_CREATED)
async def issue_jury_link(
    response: Response,
    _admin: RealAdmin,
    _csrf: CsrfUser,
    store: Store,
    settings: Annotated[Settings, Depends(get_settings)],
    expires_at: AwareDatetime | None = None,
) -> IssuedJuryLink:
    """Issue a short-lived link that can be redeemed only once.

    Args:
        response: outgoing response with caching disabled.
        store: link store.
        settings: environment and public URL of the panel.
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
    origin = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    response.headers.update(NO_STORE)
    return IssuedJuryLink(
        url=f"{origin.rstrip('/')}{JURY_LANDING}#{token}", expires_at=deadline
    )
