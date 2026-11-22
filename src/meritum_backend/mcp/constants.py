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

SEARCH_TOOL_NAME: Final = "search_sources"
"""The tool that searches the audited source corpus."""

SEARCH_TOOL_DESCRIPTION: Final = (
    "Szuka w katalogu źródeł publicznych (polskie media, instytucje, "
    "fact-checkerzy) fragmentów pasujących do zapytania, bez pełnego "
    "sprawdzenia twierdzenia. Zwraca krótkie fragmenty z tytułem, wydawcą, "
    "datą publikacji, linkiem i wersją korpusu. To nie jest werdykt: do oceny "
    "prawdziwości użyj narzędzia check_claim. Podawaj użytkownikowi linki do źródeł."
)
"""Tool description the chat app shows its model."""

QUERY_MAX_CHARS: Final = 500
"""Longest search query; a claim to check is longer, a search is a few words."""

QUERY_DESCRIPTION: Final = "Zapytanie do katalogu źródeł, do 500 znaków."
"""Description of the tool's ``query`` argument."""

RESULT_LIMIT: Final = 5
"""Most fragments one search returns."""

FRAGMENT_MAX_CHARS: Final = 400
"""Longest fragment of a source text a result carries; the full text stays in the
system (US-KOR-05)."""

ELLIPSIS: Final = "…"
"""Ends a fragment that was cut."""

BLANK_QUERY_TEXT: Final = "Zapytanie nie może być puste."
"""Tool error for a blank query."""

RATE_LIMITED_TEXT: Final = "Za dużo wyszukiwań. Spróbuj ponownie za minutę."
"""Tool error when the address is over its search limit."""

CORPUS_UNAVAILABLE_TEXT: Final = (
    "Katalog źródeł jest chwilowo niedostępny. Spróbuj ponownie za chwilę."
)
"""Tool error when the corpus or its embeddings failed, or the snapshot is unknown."""

SOURCE_QUERY: Final = """
SELECT source_id, domain, publisher_id, url
FROM corpus.documents
WHERE source_id = ANY(%s)
"""
"""Read-only lookup of the link and publisher of found sources (infra/004)."""

INTROSPECTION_TIMEOUT_SECONDS: Final = 3.0
"""How long a token check waits for the OAuth server before it denies access."""

API_KEY_HEADER: Final = "X-API-Key"
"""Header for connectors that send a plain key; else ``Authorization: Bearer``."""

REALM: Final = "meritum-mcp"
"""Realm of the WWW-Authenticate challenge."""

UNAUTHORIZED_TEXT: Final = (
    "Wymagane uwierzytelnienie. Wyślij klucz API w nagłówku "
    "'Authorization: Bearer <klucz>' albo 'X-API-Key: <klucz>', albo token "
    "dostępu OAuth w nagłówku 'Authorization: Bearer <token>'."
)
"""Body of the 401 answer: how to authenticate, never what was wrong with a secret."""

RATE_LIMITED_CHECK_TEXT: Final = "Za dużo sprawdzeń. Spróbuj ponownie za minutę."
"""Tool error when the client is over its check limit."""

TOO_MANY_REQUESTS: Final = 429
"""Status of POST /api/v1/checks that refused a check for a limit."""

BEARER_PREFIX: Final = "bearer "
"""Start of an ``Authorization`` value that carries a key or token, any case."""
