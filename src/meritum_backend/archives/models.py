"""Models of the archive API: a stored copy and what a caller sees.

Features:
    US-KOR-07, F-38
"""

from typing import Literal

from meritum_core.jobs.contracts import ArchiveRefusalCode
from pydantic import AwareDatetime, BaseModel, ConfigDict

type ArchiveStatus = Literal["pending", "done", "refused", "failed"]
"""Where an archiving request is."""


class ArchiveRecord(BaseModel):
    """A row of ``page_archives``: one copy's metadata; the text is in BlobStore.

    Attributes:
        archive_id: the copy's id (the workflow id).
        blob_id: where the text is stored.
        url: the final URL of the page.
        owner_id: who asked (session id or user id).
        sha256: hash of the stored bytes.
        archived_at: when the copy was made.
        expires_at: when retention deletes it.

    Features:
        US-KOR-07, F-38
    """

    model_config = ConfigDict(frozen=True)

    archive_id: str
    blob_id: str
    url: str
    owner_id: str
    sha256: str
    archived_at: AwareDatetime
    expires_at: AwareDatetime


class ArchiveView(BaseModel):
    """The answer of GET /api/v1/archives/{id}.

    Attributes:
        archive_id: the copy's id.
        status: pending, done, refused or failed.
        url: the archived page, once done.
        sha256: hash of the stored text, once done.
        archived_at: when it was made, once done.
        expires_at: when it is deleted, once done.
        refusal: why there is no copy.
        message: what the citizen is told when refused.

    Features:
        US-KOR-07, F-38
    """

    archive_id: str
    status: ArchiveStatus
    url: str | None = None
    sha256: str | None = None
    archived_at: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    refusal: ArchiveRefusalCode | None = None
    message: str | None = None


class Enqueued(BaseModel):
    """202 answer of POST /api/v1/archives.

    Attributes:
        archive_id: the id to poll at GET /api/v1/archives/{archive_id}.

    Features:
        US-KOR-07, F-38
    """

    archive_id: str
