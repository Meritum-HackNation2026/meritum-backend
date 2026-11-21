"""Builds the login provider from settings."""

from pydantic import SecretStr

from meritum_backend.auth.adapters import AuthlibLogin, OidcClient
from meritum_backend.auth.constants import (
    GOOGLE,
    GOOGLE_METADATA,
    MICROSOFT,
    MICROSOFT_METADATA,
)
from meritum_backend.auth.ports import LoginProvider
from meritum_backend.settings import Settings


def _client(
    client_id: str | None, secret: SecretStr | None, metadata_url: str
) -> OidcClient | None:
    value = secret.get_secret_value() if secret is not None else ""
    if client_id is None or not client_id or not value:
        return None
    return OidcClient(client_id, value, metadata_url)


def build_login(settings: Settings) -> LoginProvider:
    """Register every provider that has both a client id and a secret.

    Args:
        settings: the app settings.

    Returns:
        The Authlib login provider; with no provider configured, login answers 404.

    Features:
        US-MOD-05, US-SPR-10, F-25
    """
    tenant_metadata = MICROSOFT_METADATA.format(tenant=settings.microsoft_tenant)
    clients = {
        GOOGLE: _client(
            settings.google_client_id, settings.google_client_secret, GOOGLE_METADATA
        ),
        MICROSOFT: _client(
            settings.microsoft_client_id,
            settings.microsoft_client_secret,
            tenant_metadata,
        ),
    }
    return AuthlibLogin({name: c for name, c in clients.items() if c is not None})
