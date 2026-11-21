"""Notifications HTTP API: the live stream, the inbox, read marks and clearing.

Workflows save notifications through core's NotificationRepository; the stream
polls that store for the caller's new ones, so it survives restarts and reaches
every API instance and every device of a signed-in account.

Features:
    US-POW-01, US-POW-04, F-26
"""

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.sse import EventSourceResponse
from meritum_core.checks.contracts import Notification
from meritum_core.notifications import NotificationRepository

from meritum_backend.limits import TooManyChecks, admit_stream
from meritum_backend.notifications.api._recipients import Recipient, recipients
from meritum_backend.notifications.constants import (
    NOT_FOUND_DETAIL,
    POLL_SECONDS,
    STREAM_POLLS,
)

type Ticks = Callable[[], AsyncIterator[None]]
"""Starts the beat of one stream: each tick is a look for new notifications."""

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def get_notifications(request: Request) -> NotificationRepository:
    """The inbox store the app built (in memory in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        Core's NotificationRepository.

    Features:
        US-POW-01, F-26
    """
    return request.app.state.repositories.notifications


async def _poll() -> AsyncIterator[None]:
    for _ in range(STREAM_POLLS):
        await asyncio.sleep(POLL_SECONDS)
        yield


def get_ticks() -> Ticks:
    """The stream's polling beat (scripted in tests).

    Returns:
        A tick every POLL_SECONDS, STREAM_POLLS times.

    Features:
        US-POW-01, F-26
    """
    return _poll


Store = Annotated[NotificationRepository, Depends(get_notifications)]
Caller = Annotated[list[Recipient], Depends(recipients)]


async def _inbox(
    store: NotificationRepository, caller: list[Recipient]
) -> list[Notification]:
    notes = [n for kind, value in caller for n in await store.list_for(kind, value)]
    return sorted(notes, key=lambda n: n.created_at, reverse=True)


@router.get(
    "/stream",
    response_class=EventSourceResponse,
    dependencies=[Depends(admit_stream)],
    responses={status.HTTP_429_TOO_MANY_REQUESTS: {"model": TooManyChecks}},
)
async def notification_stream(
    store: Store, caller: Caller, ticks: Annotated[Ticks, Depends(get_ticks)]
) -> AsyncIterable[Notification]:
    """Push the caller's notifications that arrive while the stream is open.

    Ones already in the inbox when it opens are not sent again: the client
    lists them with GET /api/v1/notifications. The stream closes after a few
    minutes and EventSource reconnects.

    Args:
        store: the inbox store.
        caller: the session (``?session=``) and the signed-in account.
        ticks: the polling beat.

    Yields:
        Each new Notification once.

    Features:
        US-POW-01, US-POW-04, F-26
    """
    # shortcut: one saved between two connections is listed, not toasted;
    # resume from Last-Event-ID if users miss those toasts
    seen = {n.id for n in await _inbox(store, caller)}
    async for _ in ticks():
        for note in reversed(await _inbox(store, caller)):
            if note.id not in seen:
                seen.add(note.id)
                yield note


@router.get("")
async def list_notifications(store: Store, caller: Caller) -> list[Notification]:
    """List the caller's notifications, newest first.

    Args:
        store: the inbox store.
        caller: the session and the signed-in account.

    Returns:
        The notifications of both, read and unread.

    Features:
        US-POW-01, US-POW-04, F-26
    """
    return await _inbox(store, caller)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notification_id: str, store: Store, caller: Caller) -> None:
    """Mark one of the caller's notifications as read.

    Args:
        notification_id: the notification's id.
        store: the inbox store.
        caller: the session and the signed-in account.

    Raises:
        HTTPException: 404 when no notification with that id is the caller's.

    Features:
        US-POW-01, F-26
    """
    if all(n.id != notification_id for n in await _inbox(store, caller)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND_DETAIL)
    await store.mark_read(notification_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_notifications(store: Store, caller: Caller) -> None:
    """Delete every notification of the caller's session and account.

    Args:
        store: the inbox store.
        caller: the session and the signed-in account.

    Features:
        US-POW-01, US-BEZ-05, F-26
    """
    for kind, value in caller:
        await store.delete_for(kind, value)
