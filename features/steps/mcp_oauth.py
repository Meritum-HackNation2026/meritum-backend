"""Steps for MCP OAuth discovery (security.feature)."""

import re

from behave import then
from behave.runner import Context
from fastapi.testclient import TestClient


@then("nagłówek WWW-Authenticate prowadzi do serwera autoryzacji z PKCE S256")
def discovery(context: Context) -> None:
    """Follow resource_metadata to the authorization server metadata.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """
    challenge = context.reply.headers["WWW-Authenticate"]
    found = re.search(r'resource_metadata="([^"]+)"', challenge)
    assert found is not None, challenge
    http = TestClient(context.app)
    path = "/" + found.group(1).split("/", 3)[3]
    resource = http.get(path).json()
    issuer = resource["authorization_servers"][0]
    server = http.get("/.well-known/oauth-authorization-server").json()
    assert server["issuer"] == issuer
    assert server["code_challenge_methods_supported"] == ["S256"]
