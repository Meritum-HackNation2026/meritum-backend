"""Staff API of the moderators' notification target (US-MOD-01).

Features:
    US-POW-05, US-MOD-01, F-26
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from meritum_backend.auth.api import CsrfUser
from meritum_backend.notifications.constants import CONFIG_NOT_SET_DETAIL
from meritum_backend.notifications.models import NotifierConfig, NotifierConfigView
from meritum_backend.notifications.ports import NotifierConfigStore
from meritum_backend.staff.api import Admin, RealAdmin

router = APIRouter(prefix="/api/v1/staff/notifications", tags=["staff"])


def get_configs(request: Request) -> NotifierConfigStore:
    """The target store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's notifier configuration store.

    Features:
        US-MOD-01, F-26
    """
    return request.app.state.notifier_configs


Configs = Annotated[NotifierConfigStore, Depends(get_configs)]


def _view(config: NotifierConfig) -> NotifierConfigView:
    return NotifierConfigView(
        kind=config.kind, url=config.url, secret_set=config.secret is not None
    )


@router.get("")
async def read_target(_admin: Admin, configs: Configs) -> NotifierConfigView:
    """The target moderators are told on, without its secret.

    Args:
        _admin: the signed-in administrator.
        configs: the target store.

    Returns:
        The kind, the address and whether a secret is stored.

    Raises:
        HTTPException: 404 when no target was set.

    Features:
        US-MOD-01, F-26
    """
    config = await configs.get()
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CONFIG_NOT_SET_DETAIL)
    return _view(config)


@router.put("")
async def set_target(
    config: NotifierConfig, _admin: RealAdmin, _csrf: CsrfUser, configs: Configs
) -> NotifierConfigView:
    """Choose webhook, Google Chat or e-mail; it replaces the previous target.

    Args:
        config: the target (a webhook's secret signs its body).
        _admin: the signed-in administrator.
        _csrf: the account, CSRF checked.
        configs: the target store.

    Returns:
        What was stored, without the secret.

    Features:
        US-MOD-01, F-26
    """
    await configs.save(config)
    return _view(config)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_target(_admin: RealAdmin, _csrf: CsrfUser, configs: Configs) -> None:
    """Stop external notifications; the staff inbox keeps working.

    Args:
        _admin: the signed-in administrator.
        _csrf: the account, CSRF checked.
        configs: the target store.

    Features:
        US-MOD-01, F-26
    """
    await configs.delete()
