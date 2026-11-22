"""Who asks about a copy: the caller's ids, the moderator flag and the stores.

Features:
    US-KOR-07, F-38
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from meritum_core.shared.blobs import BlobStore

from meritum_backend.archives.models import ArchiveRecord
from meritum_backend.archives.ports import ArchiveStore
from meritum_backend.auth.api import OptionalUser
from meritum_backend.checks import SESSION_HEADER
from meritum_backend.checks.api import get_blobs
from meritum_backend.staff.api import Staff, StaffGate
from meritum_backend.staff.constants import EVERY_ROLE


def get_archive_store(request: Request) -> ArchiveStore:
    """The archive store the app built (overridden in tests).

    Args:
        request: the current request (holds the app state).

    Returns:
        The app's archive store.

    Features:
        US-KOR-07, F-38
    """
    return request.app.state.archives


async def is_moderator(request: Request, account: OptionalUser, staff: Staff) -> bool:
    """Whether the caller is signed in as staff (any panel role).

    Args:
        request: the current request.
        account: the signed-in account, if any.
        staff: the staff account store.

    Returns:
        True for a moderator, analyst or administrator.

    Features:
        US-KOR-07, F-38
    """
    if account is None:
        return False
    try:
        await StaffGate(EVERY_ROLE)(request, account, staff)
    except HTTPException:
        return False
    return True


def caller_ids(
    account: OptionalUser,
    session: Annotated[str | None, Header(alias=SESSION_HEADER)] = None,
) -> list[str]:
    """Every id the caller speaks for: its account first, then its session.

    Args:
        account: the signed-in account, if any.
        session: the session id from the X-Meritum-Session header.

    Returns:
        Zero, one or two ids.

    Features:
        US-KOR-07, F-38
    """
    ids = [] if account is None else [account.user_id]
    return ids if session is None else [*ids, session]


Store = Annotated[ArchiveStore, Depends(get_archive_store)]
Callers = Annotated[list[str], Depends(caller_ids)]
Moderator = Annotated[bool, Depends(is_moderator)]


@dataclass(frozen=True)
class Access:
    """Who asks about a copy, and where copies are kept.

    Attributes:
        store: the copies' metadata.
        blobs: the blob store with the text.
        callers: the caller's account and session ids.
        moderator: whether the caller is staff.

    Features:
        US-KOR-07, F-38
    """

    store: ArchiveStore
    blobs: BlobStore
    callers: list[str]
    moderator: bool

    async def visible(self, archive_id: str) -> ArchiveRecord | None:
        """The copy, when it exists and the caller may see it.

        Args:
            archive_id: the copy's id.

        Returns:
            The copy, or None (missing and forbidden look the same).
        """
        record = await self.store.get(archive_id)
        if record is None or not self.may_see(record.owner_id):
            return None
        return record

    def may_see(self, owner_id: str) -> bool:
        """Whether the caller owns ``owner_id``'s copies or is a moderator.

        Args:
            owner_id: who asked for the copy.

        Returns:
            True for the owner or staff.
        """
        return self.moderator or owner_id in self.callers


def get_access(
    store: Store,
    blobs: Annotated[BlobStore, Depends(get_blobs)],
    callers: Callers,
    moderator: Moderator,
) -> Access:
    """Bundle the caller and the stores for one archive request.

    Args:
        store: the copies' metadata.
        blobs: the blob store.
        callers: the caller's account and session ids.
        moderator: whether the caller is staff.

    Returns:
        The access of this request.

    Features:
        US-KOR-07, F-38
    """
    return Access(store, blobs, callers, moderator)


Caller = Annotated[Access, Depends(get_access)]
