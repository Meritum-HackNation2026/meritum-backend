"""Models of the limits slice.

Features:
    US-BEZ-02, US-WDR-03, F-20, F-23
"""

from typing import NamedTuple


class Refusal(NamedTuple):
    """Why a new check may not start, and when to try again.

    Attributes:
        message_key: copy/pl.json key of the message (no verdict).
        retry_after_seconds: the Retry-After of the 429 answer.

    Features:
        US-BEZ-02, US-WDR-03, F-20, F-23
    """

    message_key: str
    retry_after_seconds: int
