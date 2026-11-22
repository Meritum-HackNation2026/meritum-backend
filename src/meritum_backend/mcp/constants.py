"""Constants of the MCP channel.

Features:
    US-WDR-06, US-WTY-09, F-37, F-42, ADR-17
"""

from typing import Final

SERVER_NAME: Final = "Meritum"
"""Name the MCP server announces to chat apps."""

ENDPOINT: Final = "/mcp"
"""Streamable HTTP endpoint, no trailing slash: chat apps do not follow redirects."""

CHANNEL: Final = "mcp"
"""The channel of every check this slice starts."""

TOOL_NAME: Final = "check_claim"
"""The tool that checks one claim."""

TOOL_DESCRIPTION: Final = (
    "Sprawdza jedno twierdzenie lub pytanie o fakt w źródłach publicznych "
    "(polskie media, instytucje, fact-checkerzy). Zwraca werdykt, cytaty z "
    "linkami do źródeł i siłę dowodów. Wynik tworzy system AI: zawsze mów o tym "
    "użytkownikowi i podawaj linki do źródeł. Stany bez werdyktu "
    "(technical_failure, out_of_scope, needs_clarification) przekaż użytkownikowi "
    "tak, jak są, bez zgadywania werdyktu."
)
"""Tool description the chat app shows its model."""

TEXT_DESCRIPTION: Final = "Twierdzenie albo pytanie do sprawdzenia, do 4000 znaków."
"""Description of the tool's ``text`` argument."""

INTERNAL_URL: Final = "http://meritum.internal"
"""Base URL of the in-process call to the checks API; never leaves the process."""

CHECKS_PATH: Final = "/api/v1/checks"
"""The one checks API every channel calls (ADR-08)."""

POLL_SECONDS: Final = 1.0
"""Pause between two reads of a running check."""

WAIT_SECONDS: Final = 90.0
"""How long the tool waits for the verdict before it reports the check id."""

ACCEPTED: Final = 202
"""Status of POST /api/v1/checks that queued a check."""

TIMEOUT_TEXT: Final = "Sprawdzanie trwa dłużej niż zwykle. Spróbuj ponownie za chwilę."
"""Tool error when the check has no result within WAIT_SECONDS."""
