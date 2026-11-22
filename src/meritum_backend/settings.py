"""Settings from MERITUM_* environment variables (written by the deploy)."""

import re
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, SecretStr
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from meritum_backend.channels import ChannelHashSalt
from meritum_backend.constants import LIST_SEPARATORS, LOCAL_DB


def _emails(value: object) -> object:
    """Split a comma- or whitespace-separated list of addresses, lower-cased.

    Args:
        value: the raw value; anything but a string passes through.

    Returns:
        The addresses as a frozenset, or ``value`` unchanged.
    """
    if not isinstance(value, str):
        return value
    return frozenset(e.lower() for e in re.split(LIST_SEPARATORS, value) if e)


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
        discord_bot_token: Discord bot token; required when the Discord channel is on.
        channel_hash_salt: salt of the Discord, SMS and MCP user id hashes; an
            empty one counts as none (readiness reports it, those channels get 503).
        session_secret: key that signs the session cookie; a random one per
            process when unset (sessions then end on restart).
        public_url: public address of the API, the base of OIDC callback URLs;
            by ``env`` when unset (auth constants).
        google_client_id: OAuth client id of the Google login; no id, no Google.
        google_client_secret: OAuth client secret of the Google login.
        microsoft_client_id: Microsoft Entra application id; no id, no Microsoft.
        microsoft_client_secret: client secret of the Microsoft application.
        microsoft_tenant: Entra tenant of the login (``common``: any account).
        admin_emails: addresses that are administrators from the start (comma- or
            space-separated); the role needs an address the provider verified.
        files_dir: the files volume shared with the worker (platform, ADR-31).
        sms_gateway_username: sms-gate.app Cloud API user (Basic Auth).
        sms_gateway_password: sms-gate.app Cloud API password; with the user,
            the gateway sender exists.
        sms_gateway_webhook_signing_key: HMAC key of the gateway's webhooks; no
            key, no SMS webhook.
        sms_gateway_number: the gateway phone's own number (E.164); its SMS to
            itself are acknowledged and never answered.
        email_worker_url: address of the Cloudflare e-mail Worker (infra/009); with
            its secret, moderators can be notified by e-mail.
        email_worker_signing_secret: the HMAC secret the Worker checks.
        eval_corpus_version: the corpus snapshot evaluation runs pin.
        mcp_corpus_version: the corpus snapshot the MCP tool search_sources pins.
        eval_bundle_url: https link to a run's reproduction bundle (``{run_id}``
            is replaced); the panel's evaluation page when unset.
        sms_gsm7: reply without Polish diacritics in GSM-7 (160 characters
            per SMS instead of 70).

    Features:
        none (infrastructure)
    """

    model_config = SettingsConfigDict(env_prefix="MERITUM_", env_file=".env")

    env: str = "local"
    database_url: str = LOCAL_DB
    dbos_url: str = LOCAL_DB
    dbos_schema: str = "worker_local"
    discord_public_key: str | None = None
    discord_bot_token: SecretStr | None = None
    channel_hash_salt: ChannelHashSalt = None
    session_secret: SecretStr | None = None
    public_url: str | None = None
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: SecretStr | None = None
    microsoft_tenant: str = "common"
    admin_emails: Annotated[frozenset[str], NoDecode, BeforeValidator(_emails)] = (
        frozenset()
    )
    files_dir: Path | None = None
    eval_corpus_version: str = "current"
    mcp_corpus_version: str = "current"
    eval_bundle_url: str | None = None
    sms_gateway_username: str | None = None
    sms_gateway_password: SecretStr | None = None
    sms_gateway_webhook_signing_key: SecretStr | None = None
    sms_gateway_number: str | None = None
    email_worker_url: str | None = None
    email_worker_signing_secret: SecretStr | None = None
    sms_gsm7: bool = False


def get_settings() -> Settings:
    """Settings dependency (overridden in tests).

    Returns:
        Settings read from the environment.

    Features:
        none (infrastructure)
    """
    return Settings()
