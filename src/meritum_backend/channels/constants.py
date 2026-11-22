"""Copy for results without verdicts, shared by Discord and SMS.

copy/pl.json (synced from design-system, never edited here).
"""

from typing import Final

STATUS_HINTS: Final = {
    "needs_clarification": (
        "Nie wiemy, które twierdzenie sprawdzić. Napisz je jednym zdaniem."
    ),
    "out_of_scope": (
        "Sprawdzamy twierdzenia o faktach z życia publicznego. Tego pytania nie"
        " obsługujemy."
    ),
    "technical_failure": (
        "Nie udało się sprawdzić. To nie jest ocena treści. Spróbuj za kilka minut."
    ),
}
"""copy/pl.json status_hint.*: a status that is not a verdict, without a code."""

OUT_OF_SCOPE_CODES: Final = {
    "image": (
        "Na razie nie sprawdzamy obrazów. Przepisz tekst z obrazka albo wklej link"
        " do źródła."
    ),
    "audio": "Tego nagrania nie sprawdzimy. Wyślij inne nagranie albo przepisz tekst.",
    "not_informational": (
        "Nie widzimy tu twierdzenia o faktach z życia publicznego, więc nie mamy"
        " czego sprawdzić. Napisz jednym zdaniem, co chcesz sprawdzić."
    ),
}
"""copy/pl.json out_of_scope_code.*."""

FAILURE_CODES: Final = {
    "provider_unavailable": (
        "Usługa, z której korzystamy przy sprawdzaniu, nie odpowiada. To nie jest"
        " ocena treści. Spróbuj za kilka minut."
    ),
    "web_search_unavailable": (
        "Nie udało się wyszukać świeżych publikacji, a bez nich nie damy odpowiedzi."
        " To nie jest ocena treści. Spróbuj za kilka minut."
    ),
    "transcription_failed": (
        "Nie udało się zamienić nagrania na tekst. To nie jest ocena treści. Wyślij"
        " nagranie jeszcze raz albo przepisz tekst."
    ),
    "url_unavailable": (
        "Nie udało się otworzyć strony z linku: jest niedostępna albo wymaga"
        " logowania. To nie jest ocena treści. Wklej tekst."
    ),
    "not_ready": (
        "Meritum jeszcze się uruchamia i nie przyjmuje sprawdzeń. To nie jest ocena"
        " treści. Spróbuj za kilka minut."
    ),
}
"""copy/pl.json failure_code.*."""
