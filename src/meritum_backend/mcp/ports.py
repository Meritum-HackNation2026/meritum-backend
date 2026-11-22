"""Ports of the MCP channel.

Features:
    US-WDR-06, US-WTY-09, F-37, F-42, ADR-32
"""

from collections.abc import Collection, Mapping
from typing import Protocol

from pydantic import BaseModel


class SourceInfo(BaseModel, frozen=True):
    """What the catalogue knows about a source document.

    Attributes:
        title: the document title; None until the corpus stores titles.
        publisher: the catalogue publisher id.
        url: the document link.

    Features:
        US-WDR-06, F-37, ADR-32
    """

    title: str | None = None
    publisher: str | None = None
    url: str | None = None


class SourceCatalogue(Protocol):
    """Looks up title, publisher and link of corpus sources (port).

    Features:
        US-WDR-06, F-37, ADR-32
    """

    async def describe(self, source_ids: Collection[str]) -> Mapping[str, SourceInfo]:
        """Describe sources.

        Args:
            source_ids: corpus document ids.

        Returns:
            Info per known id; unknown ids are absent.
        """
        ...
