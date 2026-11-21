"""BlobStoreProbe through core's factory: names the unset ``MERITUM_BLOB_*`` variables.

Features:
    US-WDR-08, F-30, ADR-31
"""

from meritum_core.shared.blobs.constants import ENV_PREFIX
from meritum_core.shared.blobs.errors import BlobError
from meritum_core.shared.blobs.factory import build_blob_store
from meritum_core.shared.blobs.settings import BlobSettings
from pydantic import ValidationError

from meritum_backend.health.constants import BLOB_PROVIDER_FIELDS, BLOB_STORE
from meritum_backend.health.models import Problems


def _env_name(field: str | int) -> str:
    return f"{ENV_PREFIX}{field}".upper()


class BlobStoreConfig:
    """Builds the blob store from ``MERITUM_BLOB_*`` with core's factory.

    Features:
        US-WDR-08, F-30, ADR-31
    """

    def problems(self) -> Problems:  # ruff: ignore[no-self-use] -- implements BlobStoreProbe
        """What the ``MERITUM_BLOB_*`` configuration lacks.

        Returns:
            The unset variables, or the blob store as unavailable when building
            failed for another reason.
        """
        try:
            settings = BlobSettings()
        except ValidationError as exc:
            return Problems([_env_name(e["loc"][0]) for e in exc.errors()], [])
        try:
            build_blob_store(settings)
        except BlobError:
            return Problems([_env_name(BLOB_PROVIDER_FIELDS[settings.provider])], [])
        except Exception:  # ruff: ignore[blind-except] -- any SDK error (e.g. GCS without credentials) means unavailable; the name is enough
            return Problems([], [BLOB_STORE])
        return Problems([], [])
