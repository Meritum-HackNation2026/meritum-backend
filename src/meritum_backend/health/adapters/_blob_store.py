"""BlobStoreProbe through the API's own blob factory: names the unset variables.

Features:
    US-WDR-08, F-30, ADR-31
"""

from meritum_core.shared.blobs import BlobError, BlobSettings
from pydantic import ValidationError

from meritum_backend.checks.factory import build_blobs
from meritum_backend.health.constants import (
    BLOB_ENV_PREFIX,
    BLOB_PROVIDER_FIELDS,
    BLOB_STORE,
)
from meritum_backend.health.models import Problems
from meritum_backend.settings import Settings


def _env_name(field: str | int) -> str:
    return f"{BLOB_ENV_PREFIX}{field}".upper()


class BlobStoreConfig:
    """Builds the blob store the way the app does (``build_blobs``).

    The files volume (``MERITUM_FILES_DIR``) wins; otherwise ``MERITUM_BLOB_*``.

    Args:
        settings: the app settings.

    Features:
        US-WDR-08, F-30, ADR-31
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def problems(self) -> Problems:
        """What the blob store configuration lacks.

        Returns:
            The unset variables, or the blob store as unavailable when building
            failed for another reason.
        """
        try:
            build_blobs(self._settings)
        except ValidationError as exc:
            return Problems([_env_name(e["loc"][0]) for e in exc.errors()], [])
        except BlobError:  # no files volume, so MERITUM_BLOB_PROVIDER is set
            field = BLOB_PROVIDER_FIELDS.get(BlobSettings().provider)
            return (
                Problems([_env_name(field)], [])
                if field is not None
                else Problems([], [BLOB_STORE])
            )
        except Exception:  # ruff: ignore[blind-except] -- any SDK error (e.g. GCS without credentials) means unavailable; the name is enough
            return Problems([], [BLOB_STORE])
        return Problems([], [])
