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


class McpClient(BaseModel, frozen=True):
    """A client that passed authentication.

    Attributes:
        client_id: stable id of the connector (key label or OAuth client id);
            hashed with the salt before it is stored or counted (US-BEZ-06).

    Features:
        US-WDR-06, US-BEZ-02, F-37
    """

    client_id: str


class McpAuthenticator(Protocol):
    """Recognises an MCP client by its credential (port).

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """

    async def authenticate(self, credential: str) -> McpClient | None:
        """Check an API key or an OAuth access token.

        Args:
            credential: the secret from the request header.

        Returns:
            The client, or None when the credential is unknown, expired or
            the provider cannot be reached (fail closed).
        """
        ...
