"""Builds the BlobStore that keeps uploaded recordings (core factory, ADR-31).

Features:
    US-SPR-11, F-08, ADR-31
"""

from meritum_core.shared.blobs import (
    BlobProvider,
    BlobSettings,
    BlobStore,
    build_blob_store,
)
from pydantic import ValidationError

from meritum_backend.checks.constants import LOCAL_ENV
from meritum_backend.settings import Settings


def build_blobs(settings: Settings) -> BlobStore:
    """Build the store: the files volume, else ``MERITUM_BLOB_*``.

    Args:
        settings: the backend settings; ``files_dir`` is the volume shared with
            the worker of this environment.

    Returns:
        The filesystem adapter on ``files_dir``; the adapter ``MERITUM_BLOB_PROVIDER``
        names (``gcs`` in the cloud); the in-memory one only locally when
        neither is set.

    Raises:
        ValidationError: outside ``local``, neither is set or the provider is
            unknown, so a misconfigured deploy fails at startup.

    Features:
        US-SPR-11, F-08, ADR-31
    """
    if settings.files_dir is not None:
        provider = BlobProvider.FILESYSTEM
        return build_blob_store(
            BlobSettings(provider=provider, directory=settings.files_dir)
        )
    try:
        blob_settings = BlobSettings()
    except ValidationError:
        if settings.env != LOCAL_ENV:
            raise
        # shortcut: locally (tests, the API alone) memory, which the worker cannot
        # read; set MERITUM_FILES_DIR to run recordings end to end.
        blob_settings = BlobSettings(provider=BlobProvider.MEMORY)
    return build_blob_store(blob_settings)
