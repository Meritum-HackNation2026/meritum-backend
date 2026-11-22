"""Builds the corpus search and source catalogue of the MCP channel from settings.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-32
"""

from meritum_core.corpus import (
    CorpusProvider,
    CorpusSearchPort,
    CorpusSettings,
    build_corpus_search,
)
from meritum_core.shared.embeddings import EmbeddingsSettings, build_embeddings

from meritum_backend.mcp.adapters import (
    AnyOfAuthenticator,
    ApiKeyAuthenticator,
    IntrospectionAuthenticator,
    MemorySourceCatalogue,
    PostgresSourceCatalogue,
)
from meritum_backend.mcp.ports import McpAuthenticator, SourceCatalogue
from meritum_backend.mcp.settings import McpSettings


def build_corpus_reader() -> tuple[CorpusSearchPort, SourceCatalogue]:
    """Build the search port and catalogue the ``MERITUM_CORPUS_*`` variables name.

    Returns:
        The corpus search port (ADR-32) and a read-only source catalogue; both
        in memory (empty) unless the provider is postgres.

    Features:
        US-WDR-06, F-37, ADR-32
    """
    settings = CorpusSettings()
    search = build_corpus_search(settings, build_embeddings(EmbeddingsSettings()))
    if (
        settings.provider is CorpusProvider.POSTGRES
        and settings.database_url is not None
    ):
        return search, PostgresSourceCatalogue(settings.database_url.get_secret_value())
    return search, MemorySourceCatalogue()


def _keys(raw: str) -> dict[str, str]:
    # "label=key,label2=key2"; a key may contain "=", a label may not
    pairs = (item.partition("=") for item in raw.split(","))
    return {label.strip(): key.strip() for label, _, key in pairs if label and key}


def build_mcp_auth(settings: McpSettings | None = None) -> McpAuthenticator:
    """Build the authenticator the ``MERITUM_MCP_*`` variables name.

    Args:
        settings: the settings; read from the environment when omitted.

    Returns:
        Keys and OAuth introspection, whichever are configured; with neither,
        nobody is let in.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """
    settings = settings or McpSettings()
    parts: list[McpAuthenticator] = []
    if keys := _keys(settings.api_keys.get_secret_value()):
        parts.append(ApiKeyAuthenticator(keys))
    url, client_id = settings.oauth_introspection_url, settings.oauth_client_id
    secret = (
        settings.oauth_client_secret.get_secret_value()
        if settings.oauth_client_secret is not None
        else ""
    )
    if bool(url) and bool(client_id) and bool(secret):
        parts.append(IntrospectionAuthenticator(url, client_id, secret))
    return AnyOfAuthenticator(parts)
