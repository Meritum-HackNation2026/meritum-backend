"""Discord constants: application commands and interaction codes.

``COMMANDS`` is registered by scripts/register_discord_commands.py.

Features:
    US-WTY-06, US-BEZ-05, US-BEZ-06, US-BEZ-07, F-03, F-20, F-21
"""

from typing import Any, Final

CHECK: Final = "sprawdz"
"""Slash command name: ``/sprawdz tekst:<text or link>``."""

CHECK_MESSAGE: Final = "Sprawdź w Meritum"
"""Message command name: the Apps menu on any message."""

DELETE_MY_DATA: Final = "usun-moje-dane"
"""Slash command name: delete this Discord user's check records."""

TEXT_OPTION: Final = "tekst"
"""Option of the slash command that carries the text to check."""

PUBLIC_OPTION: Final = "publiczne"
"""Boolean option of ``/sprawdz``: show the result to the whole channel."""

PUBLIC_OPTION_TEXT: Final = "Pokaż wynik wszystkim na kanale"
"""copy/pl.json discord.public_option."""

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
            },
            {
                "type": 5,
                "name": PUBLIC_OPTION,
                "description": "Show the result to everyone in the channel",
                "description_localizations": {"pl": PUBLIC_OPTION_TEXT},
                "required": False,
            },
        ],
        **_WHERE,
    },
    {"name": CHECK_MESSAGE, "type": 3, **_WHERE},
    {
        "name": DELETE_MY_DATA,
        "type": 1,
        "description": "Delete your check records",
        "description_localizations": {
            "pl": "Usuń zapisy twoich sprawdzeń",
        },
        **_WHERE,
    },
]
"""Global application commands of the Meritum Discord app."""

DELETED: Final = "Usunęliśmy zapisy twoich sprawdzeń."
"""copy/pl.json channel_privacy.deleted: confirm /usun-moje-dane."""

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
"""Reads before a reply gives up (10 minutes; the interaction token lives 15)."""

FINISHED_STATUSES: Final = frozenset(
    {"SUCCESS", "ERROR", "CANCELLED", "MAX_RECOVERY_ATTEMPTS_EXCEEDED"}
)
"""DBOS workflow statuses that will not change any more."""

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

RESULT_TITLE: Final = "Wynik sprawdzenia: {claims}"
"""copy/pl.json discord.result_title."""

CARD_BUTTON: Final = "Pełna karta"
"""copy/pl.json discord.card_button: label of the link button."""

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

SEEN_MESSAGES: Final = 1000
"""Message ids the Gateway remembers, so a resumed session never answers twice."""

VOICE_HOSTS: Final = frozenset({"cdn.discordapp.com", "media.discordapp.net"})
"""Hosts a voice message may be downloaded from: Discord's CDN only, so a forged
attachment URL never makes the bot fetch an arbitrary address."""

VOICE_TIMEOUT_SECONDS: Final = 30.0
"""Longest wait for a voice message download (the signed URL expires quickly)."""

TRANSCRIPT: Final = "Transkrypcja nagrania: „{text}”"
"""copy/pl.json result.transcript as a line before the transcript."""

TRANSCRIPT_HINT: Final = (
    "Transkrypcję przygotował system automatycznie. Może zawierać błędy."
)
"""copy/pl.json result.transcript_hint."""

AUDIO_REFUSALS: Final = {
    "errors.audio_too_large": (
        "Plik jest za duży. Wyślij nagranie do {max_mb} MB albo je przytnij."
    ),
    "errors.audio_too_long": (
        "Nagranie jest za długie. Wyślij najwyżej {max_minutes} min albo je przytnij."
    ),
    "out_of_scope_code.audio": (
        "Tego nagrania nie sprawdzimy. Wyślij inne nagranie albo przepisz tekst."
        " Przyjmujemy pliki: {formats}."
    ),
}
"""copy/pl.json errors.audio_* and out_of_scope_code.audio (+ limitation_code
audio_format_unsupported): why a recording got no verdict."""

GATEWAY_INTENTS: Final = ("guilds", "guild_messages", "dm_messages")
"""Non-privileged intents only: a message that mentions the bot or is sent to it
in a DM carries its content without MESSAGE_CONTENT."""

BOT_TOKEN_MISSING: Final = (
    "MERITUM_DISCORD_BOT_TOKEN is not set: the Gateway cannot start"  # ruff: ignore[hardcoded-password-string]
)
"""Logged, then the process exits with 1."""
