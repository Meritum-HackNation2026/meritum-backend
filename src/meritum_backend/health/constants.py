"""Constants of the health slice (readiness of the API and of the worker).

Features:
    US-WDR-08, US-BEZ-03, F-30
"""

from typing import Final

from meritum_core.shared.blobs import BlobProvider

SALT_ENV: Final = "MERITUM_CHANNEL_HASH_SALT"
"""Variable with the salt of channel user id hashes; required in every env."""

BOT_TOKEN_ENV: Final = "MERITUM_DISCORD_BOT_TOKEN"  # ruff: ignore[hardcoded-password-string] -- a variable name, not a token
"""Variable with the Discord bot token; required when the Discord channel is on."""

BLOB_ENV_PREFIX: Final = "MERITUM_BLOB_"
"""Prefix of the blob store variables (``ENV_PREFIX`` of core's BlobSettings)."""

BLOB_PROVIDER_FIELDS: Final = {
    BlobProvider.FILESYSTEM: "directory",
    BlobProvider.GCS: "bucket",
}
"""BlobSettings field each provider needs; its MERITUM_BLOB_* variable is reported."""

BLOB_STORE: Final = "blob_store"
"""Provider name reported when the blob store is configured but cannot be built."""

WORKFLOW_ID_PREFIX: Final = "readiness-"
"""Prefix of the ids of the `readiness` workflows the API enqueues."""

HEALTH_WORKER_WAIT_SECONDS: Final = 1.0
"""How long GET /api/v1/health waits for the worker's readiness event."""

STARTUP_WORKER_WAIT_SECONDS: Final = 60.0
"""How long the startup log waits for the worker's readiness event."""

READY_CACHE_SECONDS: Final = 30.0
"""How long a check request reuses the last readiness report before probing again."""

NOT_READY_CODE: Final = "not_ready"
"""Failure code of a check refused while the service is not ready (core contract v4)."""

NOT_READY_KEY: Final = "status_hint.technical_failure"
"""copy/pl.json key shown when the service is not ready; it names no keys."""

DATABASE_CONNECT_TIMEOUT_SECONDS: Final = 3
"""How long the readiness probe waits to connect to the API's database."""

WORKER_REFRESH_SECONDS: Final = 60.0
"""Age of the worker report after which the API enqueues a new `readiness` workflow."""

WORKER_EXPIRY_SECONDS: Final = 2 * WORKER_REFRESH_SECONDS
"""Age after which the worker's last report no longer counts: it stopped answering."""
