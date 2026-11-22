"""Issue, list and revoke reusable demo links for technical accounts."""

import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AwareDatetime, BaseModel, Field, SecretStr

from meritum_backend.auth.api import CsrfUser
from meritum_backend.auth.constants import LOCAL_URL, PUBLIC_URLS, TOKEN_BYTES
from meritum_backend.jury.api._demo import demo_hash, require_demo_env
from meritum_backend.jury.api._redemption import Store
from meritum_backend.jury.constants import (
    DEMO_ID_PATTERN,
    DEMO_PATH,
    JURY_LINK_MAX_TTL,
    JURY_LINK_TTL,
    NO_STORE,
)
from meritum_backend.jury.ports import DemoAccount, DemoLink, JuryUnavailableError
from meritum_backend.settings import Settings, get_settings
from meritum_backend.staff.api import RealAdmin

router = APIRouter()


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


class DemoLinkId(BaseModel):
    """Identify a demo link without its URL.

    Attributes:
        id: the identifier returned by the staff API.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    id: Annotated[str, Field(pattern=DEMO_ID_PATTERN)]


class IssuedDemoLink(BaseModel):
    """The administrator's only copy of the link.

    Attributes:
        id: identifier for managing the link.
        url: backend address that signs the visitor in.
        expires_at: last moment the link works.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """

    id: str
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
    require_demo_env(settings)
    now = datetime.now(UTC)
    deadline = body.expires_at or now + JURY_LINK_TTL
    if not now < deadline <= now + JURY_LINK_MAX_TTL:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid deadline")
    token = secrets.token_urlsafe(TOKEN_BYTES)
    digest = demo_hash(body.account, token)
    demo = DemoLink(digest.hex(), body.account, now, deadline)
    try:
        await store.save(digest, deadline, demo=demo)
    except JuryUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    origin = settings.public_url or PUBLIC_URLS.get(settings.env, LOCAL_URL)
    response.headers.update(NO_STORE)
    return IssuedDemoLink(
        id=demo.id, url=f"{origin.rstrip('/')}{DEMO_PATH}{token}", expires_at=deadline
    )


@router.post("/staff/demo-links/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_demo_link(
    body: DemoLinkRevocation | DemoLinkId,
    _admin: RealAdmin,
    _csrf: CsrfUser,
    store: Store,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Revoke a demo link so it stops working at once.

    Args:
        body: the link identifier, or the original account and token.
        _admin: the signed-in administrator (not a demo session).
        _csrf: the account, CSRF checked.
        store: link store.
        settings: environment.

    Raises:
        HTTPException: 404 when no such link exists, 503 on storage failure.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    require_demo_env(settings)
    try:
        if isinstance(body, DemoLinkId):
            removed = await store.remove(bytes.fromhex(body.id), demo_only=True)
        else:
            removed = await store.remove(
                demo_hash(body.account, body.token.get_secret_value())
            )
    except JuryUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such demo link")


@router.get("/staff/demo-links")
async def list_demo_links(
    response: Response,
    _admin: RealAdmin,
    store: Store,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[DemoLink]:
    """List the demo links that can still be opened.

    Args:
        response: outgoing response with caching disabled.
        _admin: the signed-in administrator.
        store: link store.
        settings: environment.

    Returns:
        Demo link metadata, newest first.

    Raises:
        HTTPException: 404 outside dev or 503 on storage failure.

    Features:
        US-OBS-06, US-MOD-05, F-28, F-25
    """
    require_demo_env(settings)
    try:
        links = await store.active_demo(datetime.now(UTC))
    except JuryUnavailableError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    response.headers.update(NO_STORE)
    return links
