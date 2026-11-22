"""Constants of the SMS channel: the gateway's webhook and API, reply copy.

The Polish texts mirror design-system ``copy/pl.json`` (synced, never edited here);
the last SMS of a reply ends with the link to the full result card (#151, owner's
call, replacing the no-links decision of #29).

Features:
    US-WTY-07, US-BEZ-06, US-BEZ-07, F-32, F-21
"""

import re
from typing import Final

SIGNATURE_HEADER: Final = "X-Signature"
"""Webhook header: hex HMAC-SHA256 of the raw body followed by the timestamp."""

TIMESTAMP_HEADER: Final = "X-Timestamp"
"""Webhook header: Unix time in seconds when the gateway signed the request."""

MAX_CLOCK_SKEW_SECONDS: Final = 300
"""Signed requests older or newer than this are replayed or forged: 401."""

SMS_RECEIVED: Final = "sms:received"
"""Gateway event of an SMS; the webhook checks its ``message``."""

MMS_DOWNLOADED: Final = "mms:downloaded"
"""Gateway event of a downloaded MMS (also RCS chats); its ``body`` is the text."""

EVENT_HASH_CHARS: Final = 32
"""Hex chars of the event's SHA-256 in the check id: ``sms-`` + 32 fits in 40."""

CHANNEL: Final = "sms"
"""The channel of every check this slice starts; also the workflow id prefix."""

CHANNEL_USER: Final = "channel_user_hash"
"""SubjectKind naming an SMS sender: the salted hash of the number."""

TEXT_MAX_CHARS: Final = 4000
"""Longest checkable text (CheckRequest.text); a longer SMS gets TOO_LONG_TEXT."""

DELETE_COMMAND: Final = "USUN"
"""SMS text that deletes the number's checks; any case, ``USUŃ`` counts too."""

POLAND: Final = "48"
"""Country code of a bare national number: the gateway has a Polish SIM."""

NATIONAL_DIGITS: Final = 9
"""Digits of a Polish number without the country code."""

INTERNATIONAL_PREFIX: Final = "00"
"""Dialled before a country code instead of ``+`` (``0048...``)."""

SMS_REGION: Final = "XX"
"""Region of an SMS check for the shared limits: no Cloudflare header here."""

GATEWAY_URL: Final = "https://api.sms-gate.app/3rdparty/v1/messages"
"""sms-gate.app Cloud API: send an SMS through the gateway phone (202 with ``id``)."""

HTTP_TIMEOUT_SECONDS: Final = 10.0
"""Longest wait for the gateway API; the reply is sent after the webhook answered."""

POLL_SECONDS: Final = 5.0
"""How often a pending reply reads the check's state."""

POLL_ATTEMPTS: Final = 120
"""Reads before a reply gives up: 10 minutes, then the failure text is sent."""

FINISHED_STATUSES: Final = frozenset(
    {"SUCCESS", "ERROR", "CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"}
)
"""DBOS workflow statuses that will not change any more."""

MAX_PARTS: Final = 3
"""Most parts of one reply; sms-gate.app splits a long text into a multipart SMS."""

UCS2_PART: Final = 67
"""Characters of one part of a multipart UCS-2 SMS (Polish diacritics); 70 alone."""

GSM7_PART: Final = 153
"""Characters of one part of a multipart GSM-7 SMS; 160 alone."""

SENTENCE_GAP: Final = re.compile(r"(?<=[.!?])\s+")
"""Space after a sentence's end: a long reply is shortened between sentences."""

ELLIPSIS: Final = "…"
"""Ends a reply cut inside its first sentence; in GSM-7 mode it becomes ``...``."""

GSM7_ELLIPSIS: Final = "..."
"""ELLIPSIS in GSM-7, which has no single-character ellipsis."""

DIACRITICS: Final = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
"""Polish letters to their GSM-7 base letters (sms_gsm7 setting)."""

AI_NOTICE: Final = "Odpowiada system AI Meritum. Sprawdzamy w źródłach."
"""copy/pl.json ai_notice.sms: the first reply to a number (AI Act art. 50)."""

FAILURE_TEXT: Final = "Nie udało się sprawdzić. To nie jest ocena. Spróbuj później."
"""copy/pl.json sms.failure: the check failed or gave no verdict."""

TOO_LONG_TEXT: Final = "Za długi tekst. Wyślij krótszy albo sam link."
"""copy/pl.json sms.too_long: the SMS is over the 4000-character limit."""

VERDICTS: Final = {
    "confirmed": "Potwierdzone",
    "false": "Fałszywe",
    "misleading": "Wprowadzające w błąd",
    "insufficient_evidence": "Brak wystarczających dowodów",
    "not_verifiable": "Nie podlega weryfikacji",
}
"""copy/pl.json verdict.*: the reply is the main claim's verdict word."""
