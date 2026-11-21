"""Settings from MERITUM_* environment variables (written by the deploy)."""

from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DB = "postgresql://meritum:meritum@localhost:5432/meritum"


class Settings(BaseSettings):
    """Backend settings; defaults match `docker compose up -d db`."""

    model_config = SettingsConfigDict(env_prefix="MERITUM_", env_file=".env")

    env: str = "local"
    # Role meritum_api_<env>; its search_path is the schema api_<env>.
    database_url: str = LOCAL_DB
    # DBOS system tables of the worker (schema worker_<env>), used to enqueue jobs.
    dbos_url: str = LOCAL_DB
    dbos_schema: str = "worker_local"
