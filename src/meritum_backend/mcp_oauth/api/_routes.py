"""Registration, authorization (through the usual login) and the token endpoint.

Features:
    US-WDR-06, US-BEZ-02, F-37, ADR-17
"""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from meritum_backend.auth.api import Login, OptionalUser
from meritum_backend.auth.constants import GOOGLE
from meritum_backend.mcp_oauth import AuthorizeRequest, OAuthServer, refusal
from meritum_backend.mcp_oauth.api._metadata import Server
from meritum_backend.mcp_oauth.constants import (
    AUTHORIZE_PATH,
    COOKIE_PATH,
    NO_STORE,
    PENDING_COOKIE,
    PENDING_SECONDS,
    PUBLIC_CLIENT,
    REGISTER_PATH,
    RESUME_PATH,
    TOKEN_PATH,
)
from meritum_backend.mcp_oauth.models import RegisterRequest, TokenRequest

router = APIRouter(tags=["mcp-oauth"])


def _error(code: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status, headers=NO_STORE)


@router.post(REGISTER_PATH, status_code=201)
async def register(body: RegisterRequest, oauth: Server) -> JSONResponse:
    """RFC 7591 registration of a public client.

    Args:
        body: the client metadata.
        oauth: the OAuth server.

    Returns:
        201 with the client id, or 400 for a redirect URI that is not allowed.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    if body.token_endpoint_auth_method != PUBLIC_CLIENT:
        return _error("invalid_client_metadata")
    client_id = oauth.register(body.redirect_uris)
    if client_id is None:
        return _error("invalid_redirect_uri")
    reply = {
        "client_id": client_id,
        "redirect_uris": body.redirect_uris,
        "client_name": body.client_name,
        "token_endpoint_auth_method": PUBLIC_CLIENT,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    return JSONResponse(reply, status_code=201, headers=NO_STORE)


def _back(oauth: OAuthServer, request: AuthorizeRequest, **answer: str) -> Response:
    # RFC 9207: iss on every answer, errors included
    query = urlencode({**answer, "state": request.state, "iss": oauth.issuer})
    joiner = "&" if "?" in request.redirect_uri else "?"
    return RedirectResponse(f"{request.redirect_uri}{joiner}{query}", 302)


def _to_login(oauth: OAuthServer, request: AuthorizeRequest, login: Login) -> Response:
    if not login.providers:
        return _error("temporarily_unavailable", 503)
    # shortcut: no provider picker page; Google when configured, else the other
    provider = GOOGLE if GOOGLE in login.providers else min(login.providers)
    target = f"/api/v1/auth/login/{provider}?{urlencode({'return_to': RESUME_PATH})}"
    reply = RedirectResponse(target, 302)
    reply.set_cookie(
        PENDING_COOKIE,
        oauth.pending(request),
        max_age=PENDING_SECONDS,
        path=COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return reply


def _answer(
    oauth: OAuthServer, request: AuthorizeRequest, user: OptionalUser, login: Login
) -> Response:
    if request.redirect_uri not in oauth.redirect_uris(request.client_id):
        # never redirect to a URI the client did not register
        return _error("invalid_request")
    known = oauth.resource_known(request.resource)
    if (error := refusal(request, resource_known=known)) is not None:
        return _back(oauth, request, error=error)
    if user is None:
        return _to_login(oauth, request, login)
    code = oauth.code(
        user.user_id, request.client_id, request.redirect_uri, request.code_challenge
    )
    return _back(oauth, request, code=code)


@router.get(AUTHORIZE_PATH)
async def authorize(
    request: Annotated[AuthorizeRequest, Query()],
    oauth: Server,
    user: OptionalUser,
    login: Login,
) -> Response:
    """Authorization endpoint; a signed-out user signs in with Google or Microsoft.

    Args:
        request: the authorization request.
        oauth: the OAuth server.
        user: the signed-in account, if any.
        login: the login provider.

    Returns:
        A redirect with a code or an error, a redirect to the login, or 400
        when the client or its redirect URI is unknown.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    return _answer(oauth, request, user, login)


@router.get(RESUME_PATH)
async def resume(
    http: Request, oauth: Server, user: OptionalUser, login: Login
) -> Response:
    """Finish the authorization request kept during login.

    Args:
        http: the request with the pending cookie.
        oauth: the OAuth server.
        user: the account the login just signed in.
        login: the login provider.

    Returns:
        What the authorization endpoint answers, or 400 without a live request.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    pending = oauth.resume(http.cookies.get(PENDING_COOKIE, ""))
    reply = (
        _answer(oauth, pending, user, login)
        if pending is not None
        else _error("invalid_request")
    )
    if pending is None or user is not None:
        reply.delete_cookie(
            PENDING_COOKIE, path=COOKIE_PATH, secure=True, httponly=True
        )
    return reply


@router.post(TOKEN_PATH)
async def token(body: Annotated[TokenRequest, Form()], oauth: Server) -> JSONResponse:
    """Token endpoint: authorization code with PKCE, or a refresh token.

    Args:
        body: the token request.
        oauth: the OAuth server.

    Returns:
        The tokens, or an RFC 6749 error.

    Features:
        US-WDR-06, F-37, ADR-17
    """
    if not oauth.resource_known(body.resource):
        return _error("invalid_target")
    if body.grant_type == "authorization_code":
        sub = oauth.redeem(
            body.code, body.client_id, body.redirect_uri, body.code_verifier
        )
        tokens = oauth.tokens(sub, body.client_id) if sub is not None else None
    elif body.grant_type == "refresh_token":
        tokens = oauth.refresh(body.refresh_token, body.client_id)
    else:
        return _error("unsupported_grant_type")
    if tokens is None:
        return _error("invalid_grant")
    return JSONResponse(tokens.model_dump(), headers=NO_STORE)
