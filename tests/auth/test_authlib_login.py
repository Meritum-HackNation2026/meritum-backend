"""AuthlibLogin against a fake OIDC provider: inline metadata, mocked token endpoint."""

import asyncio
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx2
import pytest
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

from meritum_backend.auth import Account, LoginError, PendingLogin
from meritum_backend.auth.adapters import AuthlibLogin, OidcClient

ISSUER = "https://idp.test"
MS_ISSUER = "https://login.microsoftonline.com/{tenantid}/v2.0"
CLIENT_ID = "client-1"
KEY = RSAKey.generate_key(2048, parameters={"kid": "k1"})
OTHER_KEY = RSAKey.generate_key(2048, parameters={"kid": "k1"})


def metadata(issuer: str) -> dict[str, Any]:
    return {
        "issuer": issuer,
        "authorization_endpoint": "https://idp.test/authorize",
        "token_endpoint": "https://idp.test/token",
        "jwks": KeySet([KEY]).as_dict(private=False),
        "id_token_signing_alg_values_supported": ["RS256"],
    }


def claims(**override: object) -> dict[str, Any]:
    now = int(time.time())
    base = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "acc-42",
        "email": "ala@example.com",
        "email_verified": True,
        "iat": now,
        "exp": now + 300,
        "nonce": "n-1",
    }
    return base | override


def login(id_token: str | None, issuer: str = ISSUER) -> AuthlibLogin:
    def token_endpoint(request: httpx2.Request) -> httpx2.Response:
        assert b"code_verifier=v-1" in request.content
        body: dict[str, Any] = {"access_token": "at", "token_type": "Bearer"}
        if id_token is not None:
            body["id_token"] = id_token
        return httpx2.Response(200, json=body)

    client = OidcClient(
        client_id=CLIENT_ID,
        client_secret="s",  # ruff: ignore[hardcoded-password-func-arg] -- fake value
        metadata=metadata(issuer),
    )
    return AuthlibLogin(
        {"google": client}, transport=httpx2.MockTransport(token_endpoint)
    )


def sign(payload: dict[str, Any], key: RSAKey = KEY) -> str:
    return jwt.encode({"alg": "RS256", "kid": "k1"}, payload, key)


PENDING = PendingLogin(
    provider="google",
    state="s-1",
    nonce="n-1",
    code_verifier="v-1",
    redirect_uri="https://app.test/api/v1/auth/callback/google",
)


def test_valid_id_token_gives_the_account() -> None:
    account = asyncio.run(login(sign(claims())).complete("google", "code", PENDING))
    assert account == Account(
        provider="google",
        subject="acc-42",
        email="ala@example.com",
        email_verified=True,
    )


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: sign(claims(iss="https://evil.test")), id="issuer"),
        pytest.param(lambda: sign(claims(aud="someone-else")), id="audience"),
        pytest.param(lambda: sign(claims(), OTHER_KEY), id="signature"),
        pytest.param(lambda: sign(claims(exp=int(time.time()) - 3600)), id="expiry"),
        pytest.param(lambda: sign(claims(nonce="replayed")), id="nonce"),
        pytest.param(lambda: None, id="no-id-token"),
    ],
)
def test_invalid_id_token_is_refused(token: Callable[[], str | None]) -> None:
    with pytest.raises(LoginError):
        asyncio.run(login(token()).complete("google", "code", PENDING))


def test_microsoft_issuer_is_bound_to_the_tenant_claim() -> None:
    tenant = "9188040d-6c67-4c5b-b112-36a304b66dad"
    good = claims(iss=MS_ISSUER.format(tenantid=tenant), tid=tenant)
    account = asyncio.run(login(sign(good), MS_ISSUER).complete("google", "c", PENDING))
    assert account.subject == "acc-42"
    forged = claims(iss=MS_ISSUER.format(tenantid="other"), tid=tenant)
    with pytest.raises(LoginError):
        asyncio.run(login(sign(forged), MS_ISSUER).complete("google", "c", PENDING))


def test_begin_returns_url_with_state_nonce_and_pkce() -> None:
    start = asyncio.run(login(None).begin("google", PENDING.redirect_uri))
    query = parse_qs(urlparse(start.url).query)
    assert query["state"] == [start.pending.state]
    assert query["nonce"] == [start.pending.nonce]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == [PENDING.redirect_uri]
    assert start.pending.provider == "google"


def test_unknown_provider_is_refused() -> None:
    assert login(None).providers == frozenset({"google"})
    with pytest.raises(LoginError):
        asyncio.run(login(None).begin("github", PENDING.redirect_uri))
