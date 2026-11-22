"""MCP authentication settings from MERITUM_MCP_* environment variables.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    """How chat apps prove who they are; with neither set, /mcp answers 401.

    Attributes:
        api_keys: ``label=key`` pairs, comma-separated; the label is the client id.
        oauth_introspection_url: RFC 7662 endpoint of the OAuth server that
            issues tokens to chat apps.
        oauth_client_id: this API's client id at the introspection endpoint.
        oauth_client_secret: this API's client secret there.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """

    model_config = SettingsConfigDict(
        env_prefix="MERITUM_MCP_", env_file=".env", extra="ignore"
    )

    api_keys: SecretStr = SecretStr("")
    oauth_introspection_url: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: SecretStr | None = None
