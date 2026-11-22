"""Builds the corpus search and source catalogue of the MCP channel from settings.

Features:
    US-WDR-06, F-37, ADR-32
"""

from meritum_core.corpus import (
    CorpusProvider,
    CorpusSearchPort,
    CorpusSettings,
    build_corpus_search,
)
from meritum_core.shared.embeddings import EmbeddingsSettings, build_embeddings

from meritum_backend.mcp.adapters import MemorySourceCatalogue, PostgresSourceCatalogue
from meritum_backend.mcp.ports import SourceCatalogue


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
