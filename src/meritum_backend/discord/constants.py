"""Discord constants: application commands and interaction codes.

``COMMANDS`` is registered by scripts/register_discord_commands.py.

Features:
    US-WTY-06, US-BEZ-07, F-03, F-21
"""

from typing import Any, Final

CHECK: Final = "sprawdz"
"""Slash command name: ``/sprawdz tekst:<text or link>``."""

CHECK_MESSAGE: Final = "Sprawdź w Meritum"
"""Message command name: the Apps menu on any message."""

TEXT_OPTION: Final = "tekst"
"""Option of the slash command that carries the text to check."""

_WHERE: Final[dict[str, Any]] = {"contexts": [0, 1, 2], "integration_types": [0, 1]}
"""Usable in servers, DMs with the app and private channels; installable on a
server or on a user's own account (citizens can use it anywhere)."""

COMMANDS: Final[list[dict[str, Any]]] = [
    {
        "name": CHECK,
        "type": 1,
        "description": "Check a claim against described sources",
        "description_localizations": {
            "pl": "Sprawdź twierdzenie w opisanych źródłach",
        },
        "options": [
            {
                "type": 3,
                "name": TEXT_OPTION,
                "description": "Text or link to check",
                "description_localizations": {"pl": "Tekst albo link do sprawdzenia"},
                "required": True,
                "max_length": 4000,
            }
        ],
        **_WHERE,
    },
    {"name": CHECK_MESSAGE, "type": 3, **_WHERE},
]
"""Global application commands of the Meritum Discord app."""

PING: Final = 1
"""Interaction type: Discord probes the endpoint."""

APPLICATION_COMMAND: Final = 2
"""Interaction type: a slash or message command."""

PONG: Final = 1
"""Response type answering PING."""

CHANNEL_MESSAGE: Final = 4
"""Response type: a message in the channel."""

EPHEMERAL: Final = 64
"""Message flag: only the person who asked sees the answer."""

DEFERRED_CHANNEL_MESSAGE: Final = 5
"""Response type: "thinking…" now, the answer edited in later (Discord waits 3 s)."""

CHANNEL: Final = "discord"
"""The channel of every check this slice starts."""

CHANNEL_USER: Final = "channel_user_hash"
"""SubjectKind naming a Discord user: the salted hash of the user id."""

REGION: Final = "XX"
"""Region of a Discord check for the shared limits: no Cloudflare header here."""

API_URL: Final = "https://discord.com/api/v10"
"""Discord HTTP API; interaction webhooks need no bot token."""

HTTP_TIMEOUT_SECONDS: Final = 10.0
"""Longest wait for one Discord API call."""

POLL_SECONDS: Final = 3.0
"""How often a pending reply reads the check's state."""

POLL_ATTEMPTS: Final = 200
"""Reads before a reply gives up (about 14 minutes, the token lives 15)."""

MESSAGE_MAX_CHARS: Final = 2000
"""Discord limit of a message's content for bots."""

CARD_PATH: Final = "/sprawdzenie/{check_id}"
"""Path of the full result card in the web app."""

DATE_FORMAT: Final = "%d.%m.%Y"
"""Publication date of a cited source."""

# copy/pl.json (synced from design-system, never edited here)
AI_NOTICE: Final = (
    "Jestem botem Meritum, systemem AI. Sprawdzam informacje w opisanych"
    " źródłach i podaję cytaty."
)
"""copy/pl.json ai_notice.discord: first reply to a new user hash (AI Act art. 50)."""

SUMMARY: Final = "Wynik sprawdzenia: {claims}. Pełna karta: {link}"
"""copy/pl.json discord.summary."""

CLAIMS_PLURAL: Final = {
    "one": "{count} twierdzenie",
    "few": "{count} twierdzenia",
    "many": "{count} twierdzeń",
}
"""copy/pl.json discord.claims, by Polish plural category."""

SUMMARY_LINE: Final = "{verdict}: {claim}"
"""copy/pl.json discord.summary_line."""

QUOTE: Final = "„{fragment}” ({publisher}, {date})"
"""Second line of copy/pl.json discord.claim."""

UNDATED: Final = "data publikacji nieznana"
"""copy/pl.json discord.claim_undated: the date part."""

CLAIM_REVIEW: Final = "Według {publisher}: „{rating}”. {url}"
"""copy/pl.json result.claim_review plus the fact-checker's link."""

STRENGTH_LINE: Final = "Siła podstawy: {strength}"
"""Last line of copy/pl.json discord.claim."""

STRENGTH: Final = {"strong": "Mocna", "moderate": "Umiarkowana", "weak": "Słaba"}
"""copy/pl.json strength.*."""

VERDICTS: Final = {
    "confirmed": "Potwierdzone",
    "false": "Fałszywe",
    "misleading": "Wprowadzające w błąd",
    "insufficient_evidence": "Brak wystarczających dowodów",
    "not_verifiable": "Nie podlega weryfikacji",
}
"""copy/pl.json verdict.*."""

ESCALATION: Final = {
    "created": "Przekazaliśmy sprawę moderatorom (sprawa {case}).",
    "updated": "Dołączyliśmy twoje pytanie do istniejącej sprawy {case}.",
}
"""copy/pl.json escalation.*: only states that carry a case number."""

FAILURE_TEXT: Final = "Nie udało się sprawdzić. To nie jest ocena. Spróbuj później."
"""copy/pl.json sms.failure: the check failed or did not finish in time."""

ERRORS: Final = {
    "errors.empty": "Wklej tekst (co najmniej 3 znaki) albo link.",
    "errors.invalid_url": (
        "To nie wygląda na adres strony. Wklej pełny link zaczynający się od"
        " http:// albo https://."
    ),
    "errors.too_long": "Tekst jest za długi. Wklej najwyżej 4000 znaków albo sam link.",
    "errors.rate_limited": "Za dużo sprawdzeń w krótkim czasie. Spróbuj za minutę.",
    "errors.busy": (
        "Mamy teraz bardzo dużo pytań. Spróbuj za kilka minut. To nie jest ocena"
        " treści."
    ),
}
"""copy/pl.json errors.*: why a check did not start; anything else is FAILURE_TEXT."""
