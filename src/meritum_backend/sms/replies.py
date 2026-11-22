"""Reply texts: the main claim's verdict, one SMS each, no links.

Features:
    US-WTY-07, US-BEZ-07, F-32, F-21
"""

from meritum_core.checks import CheckResult

from meritum_backend.sms.constants import (
    AI_NOTICE,
    DIACRITICS,
    ELLIPSIS,
    FAILURE_TEXT,
    GSM7_ELLIPSIS,
    GSM7_LIMIT,
    UCS2_LIMIT,
    VERDICTS,
)


def one_sms(text: str, *, gsm7: bool) -> str:
    """Fit ``text`` into one SMS.

    Args:
        text: the reply.
        gsm7: drop Polish diacritics and use the 160-character GSM-7 limit;
            otherwise the text stays as is within 70 UCS-2 characters.

    Returns:
        The text, cut with an ellipsis when it is longer than one SMS.

    Features:
        US-WTY-07, F-32
    """
    if gsm7:
        text, limit, ellipsis = text.translate(DIACRITICS), GSM7_LIMIT, GSM7_ELLIPSIS
    else:
        limit, ellipsis = UCS2_LIMIT, ELLIPSIS
    if len(text) <= limit:
        return text
    return text[: limit - len(ellipsis)].rstrip() + ellipsis


def reply_texts(
    result: CheckResult | None, *, first_contact: bool, gsm7: bool
) -> list[str]:
    """The SMS replies to one check, in sending order.

    Args:
        result: the finished check's result; None when it failed.
        first_contact: the number has no earlier checks, so the AI notice goes first.
        gsm7: the sms_gsm7 setting (see ``one_sms``).

    Returns:
        One or two texts, each within one SMS.

    Features:
        US-WTY-07, US-BEZ-07, F-32, F-21
    """
    main = result.claims[0] if result is not None and result.claims else None
    verdict = VERDICTS.get(main.verdict, FAILURE_TEXT) if main else FAILURE_TEXT
    texts = [AI_NOTICE, verdict] if first_contact else [verdict]
    return [one_sms(text, gsm7=gsm7) for text in texts]
