"""API-key authentication of MCP clients.

Features:
    US-WDR-06, US-BEZ-02, F-37
"""

import hmac
from collections.abc import Mapping

from meritum_backend.mcp.ports import McpClient


class ApiKeyAuthenticator:
    """Knows a fixed set of keys, one per connector.

    Args:
        keys: client id to key.

    Features:
        US-WDR-06, US-BEZ-02, F-37
    """

    def __init__(self, keys: Mapping[str, str]) -> None:
        self._keys = dict(keys)

    async def authenticate(self, credential: str) -> McpClient | None:
        """Match the credential against every key in constant time.

        Args:
            credential: the key from the request.

        Returns:
            The client that owns the key, or None.
        """
        found = None
        for client_id, key in self._keys.items():
            if hmac.compare_digest(credential.encode(), key.encode()):
                found = McpClient(client_id=client_id)
        return found
