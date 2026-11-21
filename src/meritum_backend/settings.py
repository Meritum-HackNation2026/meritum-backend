"""Settings from MERITUM_* environment variables (written by the deploy)."""

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

    Features:
        none (infrastructure)
    """

    model_config = SettingsConfigDict(env_prefix="MERITUM_", env_file=".env")

    env: str = "local"
    database_url: str = LOCAL_DB
    dbos_url: str = LOCAL_DB
    dbos_schema: str = "worker_local"
    discord_public_key: str | None = None


def get_settings() -> Settings:
    """Settings dependency (overridden in tests).

    Returns:
        Settings read from the environment.

    Features:
        none (infrastructure)
    """
    return Settings()
