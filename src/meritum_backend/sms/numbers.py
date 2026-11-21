"""Phone numbers in one format, so one person always gets one hash.

Features:
    US-BEZ-06, US-WTY-07, F-20
"""

import re

from meritum_backend.sms.constants import (
    INTERNATIONAL_PREFIX,
    NATIONAL_DIGITS,
    POLAND,
)


def e164(raw: str) -> str:
    """Write a number as E.164; a bare 9-digit number is Polish.

    Args:
        raw: the number as the gateway or the settings give it
            (``600 700 800``, ``0048600700800``, ``+48 600-700-800``).

    Returns:
        ``+`` and digits only, e.g. ``+48600700800``.

    Features:
        US-BEZ-06, US-WTY-07, F-20
    """
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        return f"+{digits}"
    if digits.startswith(INTERNATIONAL_PREFIX):
        return f"+{digits.removeprefix(INTERNATIONAL_PREFIX)}"
    if len(digits) == NATIONAL_DIGITS:
        return f"+{POLAND}{digits}"
    return f"+{digits}"
