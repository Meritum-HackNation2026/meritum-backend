"""Settings from MERITUM_* environment variables (written by the deploy)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from meritum_backend.constants import LOCAL_DB


class Settings(BaseSettings):
    """Backend settings; defaults match `docker compose up -d db`.

    Attributes:
        env: the environment name (local, dev, prd).
        database_url: role meritum_api_<env>; its search_path is the schema api_<env>.
        dbos_url: DBOS system tables of the worker (schema worker_<env>), used to
            enqueue jobs.
        dbos_schema: the worker's DBOS system schema.
        discord_public_key: Discord app public key (hex) of this env; no key, no
            interactions endpoint.
        session_secret: key that signs the session cookie; a random one per
            process when unset (sessions then end on restart).
        public_url: public address of the API, the base of OIDC callback URLs;
            by ``env`` when unset (auth constants).
        google_client_id: OAuth client id of the Google login; no id, no Google.
        google_client_secret: OAuth client secret of the Google login.
        microsoft_client_id: Microsoft Entra application id; no id, no Microsoft.
        microsoft_client_secret: client secret of the Microsoft application.
        microsoft_tenant: Entra tenant of the login (``common``: any account).

    Features:
        none (infrastructure)
    """

    model_config = SettingsConfigDict(env_prefix="MERITUM_", env_file=".env")

    env: str = "local"
    database_url: str = LOCAL_DB
    dbos_url: str = LOCAL_DB
    dbos_schema: str = "worker_local"
    discord_public_key: str | None = None
    session_secret: SecretStr | None = None
    public_url: str | None = None
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: SecretStr | None = None
    microsoft_tenant: str = "common"


def get_settings() -> Settings:
    """Settings dependency (overridden in tests).

    Returns:
        Settings read from the environment.

    Features:
        none (infrastructure)
    """
    return Settings()
