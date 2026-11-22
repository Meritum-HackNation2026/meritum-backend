"""Intake rules of a check request: copy keys for bad input and masking.

Features:
    US-SPR-01, US-SPR-07, US-BEZ-04, F-01, F-20
"""

from collections.abc import Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from meritum_core.checks import CheckRequest
from meritum_core.security import MARKERS, PiiGatePort, mask_personal_data
from pydantic import HttpUrl
from pydantic_core import ErrorDetails

from meritum_backend.checks.constants import (
    EMPTY_KEY,
    FOREIGN_LINK,
    INVALID_URL_KEY,
    MARKER_OPEN,
    TEXT_FIELDS,
    TEXT_MAX_CHARS,
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
    if any(f in TEXT_FIELDS and e["type"] == TOO_LONG_ERROR for f, e in fields):
        return TOO_LONG_KEY
    return EMPTY_KEY


def is_unsupported_link(request: CheckRequest) -> bool:
    """Tell whether the request carries a link the worker must not fetch.

    That is a text which is a lone link with a scheme other than http(s), or a
    link with a user name or password in it.

    Args:
        request: the validated request.

    Returns:
        True for ``ftp://example.com/plik`` as text or ``https://jan:x@x.pl``.

    Features:
        US-SPR-07, F-01
    """
    text = (request.text or "").strip()
    links = (request.url, request.page_url)
    has_credentials = any(
        link is not None and (link.username or link.password) for link in links
    )
    return has_credentials or FOREIGN_LINK.fullmatch(text) is not None


async def _mask(value: str, gate: PiiGatePort) -> str:
    return (await mask_personal_data(value, gate)).text


async def masked_text(text: str, limit: int, gate: PiiGatePort) -> str:
    """Mask personal data and cut the result to ``limit`` characters.

    Markers can be longer than what they replace, so the masked text may grow
    past the limit; it is then cut before any marker the cut would split.

    Args:
        text: free text that may contain personal data.
        limit: the longest text the receiver accepts.
        gate: the personal-data masking gate.

    Returns:
        The masked text, at most ``limit`` characters long.

    Features:
        US-BEZ-04, US-MOD-06, F-20
    """
    full = await _mask(text, gate)
    if len(full) <= limit:
        return full
    cut = full[:limit]
    # a marker cut in half would reach the model as noise
    opened = cut.rfind(MARKER_OPEN)
    tail = cut[opened:]
    is_cut_marker = opened >= 0 and any(
        marker.startswith(tail) and marker != tail for marker in MARKERS
    )
    return cut[:opened] if is_cut_marker else cut


async def _masked_link(url: HttpUrl | None, gate: PiiGatePort) -> str | None:
    if url is None:
        return None
    parts = urlsplit(str(url))
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    masked_pairs = [
        (await _mask(key, gate), await _mask(value, gate)) for key, value in pairs
    ]
    if masked_pairs == pairs and not parts.fragment:
        return str(url)
    query = parts.query if masked_pairs == pairs else urlencode(masked_pairs)
    # the fragment never reaches the server, so it goes rather than being masked
    return urlunsplit(parts._replace(query=query, fragment=""))


async def masked(request: CheckRequest, gate: PiiGatePort) -> CheckRequest:
    """Return the request with personal data replaced by markers.

    Runs core's ``mask_personal_data``: the gate (a DLP service, or the null gate
    that masks nothing), then the phone, e-mail and PESEL patterns. Masks the
    text and each query parameter of the links and drops their fragment; the
    path stays as sent, so the worker still fetches the same page (a query
    with personal data is re-encoded, so ``;`` stops separating there).
    Markers can be longer than what they replace, so the masked text is cut to
    TEXT_MAX_CHARS, before any marker the cut would split: the limit applies to
    what the person sent. pydantic's ValidationError propagates when a masked
    link grew past the URL length limit.

    Args:
        request: the validated request.
        gate: the masking gate the app built from ``MERITUM_PII_*``.

    Returns:
        A new, validated request.

    Features:
        US-BEZ-04, F-20
    """
    update = {
        "text": None
        if request.text is None
        else await masked_text(request.text, TEXT_MAX_CHARS, gate),
        "url": await _masked_link(request.url, gate),
        "page_url": await _masked_link(request.page_url, gate),
    }
    # model_dump keeps every other field, also ones core adds later
    return CheckRequest.model_validate({**request.model_dump(), **update})
