"""OAuth access-token authentication of MCP clients (RFC 7662 introspection).

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

import logging

from httpx2 import AsyncClient, BasicAuth, HTTPError

from meritum_backend.mcp.constants import INTROSPECTION_TIMEOUT_SECONDS
from meritum_backend.mcp.ports import McpClient

_log = logging.getLogger(__name__)


class IntrospectionAuthenticator:
    """Asks the OAuth server whether a token is active.

    Args:
        url: the introspection endpoint.
        client_id: this API's client id there.
        client_secret: this API's client secret there.
        http: the HTTP client; tests pass one on a mock transport.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """

    def __init__(
        self,
        url: str,
        client_id: str,
        client_secret: str,
        http: AsyncClient | None = None,
    ) -> None:
        self._url = url
        self._auth = BasicAuth(client_id, client_secret)
        self._http = http or AsyncClient(timeout=INTROSPECTION_TIMEOUT_SECONDS)

    async def authenticate(self, credential: str) -> McpClient | None:
        """Introspect the token; an unreachable server means no access.

        Args:
            credential: the access token from the request.

        Returns:
            The client of an active token, or None.
        """
        try:
            answer = await self._http.post(
                self._url, data={"token": credential}, auth=self._auth
            )
            answer.raise_for_status()
            body = answer.json()
        except HTTPError, ValueError:
            # never log the token or the response body
            _log.warning("token introspection failed")
            return None
        if not isinstance(body, dict) or body.get("active") is not True:
            return None
        who = body.get("client_id") or body.get("sub")
        return McpClient(client_id=who) if isinstance(who, str) and who else None
