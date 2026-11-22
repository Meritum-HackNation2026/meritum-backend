"""Builds the signer of the MCP OAuth server.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from meritum_backend.mcp_oauth.adapters import ItsdangerousSigner
from meritum_backend.mcp_oauth.ports import TokenSigner


def build_signer(key: str) -> TokenSigner:
    """Build the signer.

    Args:
        key: the secret; the app passes its session key, so restarting with a
            random key ends every token, like every session.

    Returns:
        The itsdangerous signer.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    return ItsdangerousSigner(key)
