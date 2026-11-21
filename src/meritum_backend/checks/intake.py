"""Intake rules of a check request: copy keys for bad input and masking.

Features:
    US-SPR-01, US-SPR-07, US-BEZ-04, F-01, F-20
"""

from collections.abc import Sequence
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from meritum_core.checks import CheckRequest
from meritum_core.security import mask_personal_data
from pydantic import HttpUrl
from pydantic_core import ErrorDetails

from meritum_backend.checks.constants import (
    EMPTY_KEY,
    FOREIGN_LINK,
    INVALID_URL_KEY,
    TEXT_FIELD,
    TOO_LONG_ERROR,
    TOO_LONG_KEY,
    URL_FIELDS,
)


def message_key(errors: Sequence[ErrorDetails]) -> str:
    """Pick the copy/pl.json key that tells the person what to fix.

    Args:
        errors: pydantic's validation errors of the request body.

    Returns:
        errors.invalid_url for a bad link, errors.too_long for a long text,
        errors.empty otherwise.

    Features:
        US-SPR-01, US-SPR-07, F-01
    """
    fields = [(error["loc"][-1] if error["loc"] else "", error) for error in errors]
    if any(field in URL_FIELDS for field, _ in fields):
        return INVALID_URL_KEY
    if any(f == TEXT_FIELD and e["type"] == TOO_LONG_ERROR for f, e in fields):
        return TOO_LONG_KEY
    return EMPTY_KEY


def is_foreign_link(request: CheckRequest) -> bool:
    """Tell whether the text is a lone link with a scheme other than http(s).

    Args:
        request: the validated request.

    Returns:
        True for a text such as ``ftp://example.com/plik``.

    Features:
        US-SPR-07, F-01
    """
    text = (request.text or "").strip()
    return FOREIGN_LINK.fullmatch(text) is not None


def _masked_link(url: HttpUrl | None) -> str | None:
    if url is None:
        return None
    parts = urlsplit(str(url))
    query = mask_personal_data(unquote_plus(parts.query))
    if not query.replaced:
        return str(url)
    return urlunsplit(parts._replace(query=query.text))


def masked(request: CheckRequest) -> CheckRequest:
    """Return the request with personal data replaced by markers.

    Masks the text and the query strings of the links; the rest of a link stays
    as sent, so the worker still fetches the same page.

    Args:
        request: the validated request.

    Returns:
        A new request, validated again: pydantic's ValidationError propagates
        when the markers made the text longer than allowed.

    Features:
        US-BEZ-04, F-20
    """
    text = None if request.text is None else mask_personal_data(request.text).text
    links = {
        "url": _masked_link(request.url),
        "page_url": _masked_link(request.page_url),
    }
    return CheckRequest.model_validate({**request.model_dump(), "text": text, **links})
