"""Port of the MCP OAuth server: signs and reads its tokens.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from collections.abc import Mapping
from typing import Protocol


class TokenSigner(Protocol):
    """Turns claims into a tamper-proof string and back (port).

    Features:
        US-WDR-06, F-37, ADR-17
    """

    def sign(self, kind: str, claims: Mapping[str, object]) -> str:
        """Sign claims.

        Args:
            kind: ``client``, ``code``, ``access``, ``refresh`` or ``pending``;
                a token of one kind never reads as another.
            claims: JSON-ready claims.

        Returns:
            The signed token.
        """
        ...

    def read(self, kind: str, token: str) -> dict[str, object] | None:
        """Read a token of a kind.

        Args:
            kind: the kind it must have been signed as.
            token: the token.

        Returns:
            The claims, or None for a forged, foreign or malformed token.
        """
        ...
