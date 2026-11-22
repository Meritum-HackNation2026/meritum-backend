"""In-memory source catalogue: tests and runs without the corpus database.

Features:
    US-WDR-06, F-37, ADR-32
"""

from collections.abc import Collection, Mapping

from meritum_backend.mcp.ports import SourceInfo


class MemorySourceCatalogue:
    """SourceCatalogue over a dict.

    Args:
        sources: info per source id.

    Features:
        US-WDR-06, F-37, ADR-32
    """

    def __init__(self, sources: Mapping[str, SourceInfo] | None = None) -> None:
        self._sources = dict(sources or {})

    async def describe(self, source_ids: Collection[str]) -> Mapping[str, SourceInfo]:
        """Describe sources.

        Args:
            source_ids: corpus document ids.

        Returns:
            Info per known id.
        """
        found: dict[str, SourceInfo] = {}
        for i in source_ids:
            if i in self._sources:
                found[i] = self._sources[i]
        return found
