"""Reply texts: the main claim's verdict and the link to the full result.

Features:
    US-WTY-07, US-BEZ-07, F-32, F-21
"""

from meritum_core.checks import CheckResult

from meritum_backend.channels import non_verdict_text
from meritum_backend.sms.constants import (
    AI_NOTICE,
    DIACRITICS,
    ELLIPSIS,
    FAILURE_TEXT,
    GSM7_ELLIPSIS,
    GSM7_PART,
    MAX_PARTS,
    SENTENCE_GAP,
    UCS2_PART,
    VERDICTS,
)


def fit(text: str, *, gsm7: bool, link: str | None = None) -> str:
    """Fit ``text`` and the link into MAX_PARTS parts of one SMS.

    Args:
        text: the reply.
        gsm7: drop Polish diacritics and count 153-character GSM-7 parts;
            otherwise 67-character UCS-2 parts.
        link: goes last, after a space; never shortened.

    Returns:
        Whole sentences of ``text`` that fit, then the link. When even the
        first sentence is too long, it is cut at a word and ends with an ellipsis.

    Features:
        US-WTY-07, F-32
    """
    if gsm7:
        text, part, ellipsis = text.translate(DIACRITICS), GSM7_PART, GSM7_ELLIPSIS
    else:
        part, ellipsis = UCS2_PART, ELLIPSIS
    tail = "" if link is None else f" {link}"
    room = part * MAX_PARTS - len(tail)
    body = ""
    for sentence in SENTENCE_GAP.split(text.strip()):
        longer = f"{body} {sentence}".strip()
        if len(longer) > room:
            break
        body = longer
    if not body:
        cut = text[: room - len(ellipsis) + 1]
        body = cut.rsplit(" ", 1)[0].rstrip(" ,;:") + ellipsis
    return body + tail


def reply_texts(
    result: CheckResult | None, *, first_contact: bool, gsm7: bool, link: str
) -> list[str]:
    """The SMS replies to one check, in sending order.

    Args:
        result: the finished check's result; None when it failed. A result
            without claims is worded from copy, never from its message.
        first_contact: the number has no earlier checks, so the AI notice goes first.
        gsm7: the sms_gsm7 setting (see ``fit``).
        link: the full result card in the web app; ends the last text.

    Returns:
        One or two texts, each within MAX_PARTS parts.

    Features:
        US-WTY-07, US-BEZ-07, F-32, F-21
    """
    main = result.claims[0] if result is not None and result.claims else None
    if main is not None:
        verdict = VERDICTS.get(main.verdict, FAILURE_TEXT)
    elif result is not None:
        verdict = non_verdict_text(result) or FAILURE_TEXT
    else:
        verdict = FAILURE_TEXT
    replies = [fit(verdict, gsm7=gsm7, link=link)]
    return [fit(AI_NOTICE, gsm7=gsm7), *replies] if first_contact else replies
