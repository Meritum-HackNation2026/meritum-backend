"""TokenSigner on itsdangerous: HMAC-signed, URL-safe JSON.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from collections.abc import Mapping

from itsdangerous import BadData, URLSafeSerializer

from meritum_backend.mcp_oauth.constants import SALT_PREFIX


class ItsdangerousSigner:
    """Signs with one key and a salt per kind.

    Args:
        key: the secret key.

    Features:
        US-WDR-06, F-37, ADR-17
    """

    def __init__(self, key: str) -> None:
        self._key = key

    def _serializer(self, kind: str) -> URLSafeSerializer:
        return URLSafeSerializer(self._key, salt=SALT_PREFIX + kind)

    def sign(self, kind: str, claims: Mapping[str, object]) -> str:
        """Sign claims.

        Args:
            kind: the token kind.
            claims: JSON-ready claims.

        Returns:
            The signed token.
        """
        return str(self._serializer(kind).dumps(dict(claims)))

    def read(self, kind: str, token: str) -> dict[str, object] | None:
        """Read a token of a kind.

        Args:
            kind: the token kind.
            token: the token.

        Returns:
            The claims, or None when the signature or the format is wrong.
        """
        try:
            claims = self._serializer(kind).loads(token)
        except BadData:
            return None
        if not isinstance(claims, dict):
            return None
        return {str(name): value for name, value in claims.items()}
