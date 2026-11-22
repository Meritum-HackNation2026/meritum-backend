"""Tries several authenticators in turn.

Features:
    US-WDR-06, US-BEZ-02, F-37
"""

from collections.abc import Sequence

from meritum_backend.mcp.ports import McpAuthenticator, McpClient


class AnyOfAuthenticator:
    """The first authenticator that knows the credential wins.

    Args:
        parts: in the order they are asked; none means nobody gets in.

    Features:
        US-WDR-06, US-BEZ-02, F-37
    """

    def __init__(self, parts: Sequence[McpAuthenticator]) -> None:
        self._parts = tuple(parts)

    async def authenticate(self, credential: str) -> McpClient | None:
        """Ask each authenticator.

        Args:
            credential: the secret from the request.

        Returns:
            The first client found, or None.
        """
        for part in self._parts:
            if (client := await part.authenticate(credential)) is not None:
                return client
        return None
