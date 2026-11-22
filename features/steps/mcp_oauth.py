"""Steps for MCP OAuth discovery (security.feature)."""

import re
from http import HTTPStatus

from behave import then, when
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


@when('konektor rejestruje się z adresem powrotu "{uri}"')
def register(context: Context, uri: str) -> None:
    """Register an OAuth client with one redirect URI.

    Args:
        context: the behave context.
        uri: the redirect URI.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """
    body = {"redirect_uris": [uri]}
    context.reply = TestClient(context.app).post("/api/v1/oauth/register", json=body)


@then("rejestracja kończy się błędem invalid_redirect_uri")
def refused(context: Context) -> None:
    """The registration is refused with the RFC 7591 error.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """
    assert context.reply.status_code == HTTPStatus.BAD_REQUEST, context.reply.text
    assert context.reply.json()["error"] == "invalid_redirect_uri"


@then("rejestracja się udaje")
def registered(context: Context) -> None:
    """The registration returns a client id.

    Args:
        context: the behave context.

    Features:
        US-WDR-06, US-BEZ-02, F-37, ADR-17
    """
    assert context.reply.status_code == HTTPStatus.CREATED, context.reply.text
    assert context.reply.json()["client_id"]
